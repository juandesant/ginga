#
# GingaGw.py -- Gw display handler for the Ginga reference viewer.
#
# Eric Jeschke (eric@naoj.org)
#
# Copyright (c) Eric R. Jeschke.  All rights reserved.
# This is open-source software licensed under a BSD license.
# Please see the file LICENSE.txt for details.
#
# stdlib imports
import sys, os
import traceback
import platform
import time

# GUI imports
from ginga.gw import GwHelp, GwMain, PluginManager, Readout
from ginga.gw import Widgets, Viewers, Desktop

# Local application imports
from ginga import cmap, imap
from ginga.misc import Bunch
from ginga.canvas.types.layer import DrawingCanvas
from ginga.util.six.moves import map, zip

moduleHome = os.path.split(sys.modules[__name__].__file__)[0]
sys.path.insert(0, moduleHome)
childDir = os.path.join(moduleHome, 'plugins')
sys.path.insert(0, childDir)

## from ginga.gw import ColorBar, Readout, PluginManagerQt, \
##      QtHelp, QtMain, ImageViewCanvasQt

icon_path = os.path.abspath(os.path.join(moduleHome, '..', 'icons'))


class GingaViewError(Exception):
    pass

class GingaView(GwMain.GwMain, Widgets.Application):

    def __init__(self, logger, ev_quit):
        Widgets.Application.__init__(self, logger=logger)
        GwMain.GwMain.__init__(self, logger=logger, ev_quit=ev_quit,
                               app=self)

        ## if os.path.exists(rc_file):
        ##     self.app.setStyleSheet(rc_file)

        # defaults for height and width
        #self.default_height = min(900, self.screen_ht - 100)
        #self.default_width  = min(1600, self.screen_wd)

        self.w = Bunch.Bunch()
        self.iconpath = icon_path
        self._lastwsname = 'channels'
        self.layout = None
        self._lsize = None
        self._rsize = None
        self._cur_dialogs = []

        self.colorbar = None
        self.readout = None

    def set_layout(self, layout):
        self.layout = layout

    def get_screen_dimensions(self):
        return (self.screen_wd, self.screen_ht)

    def build_toplevel(self):

        self.font = self.getFont('fixedFont', 12)
        self.font11 = self.getFont('fixedFont', 11)
        self.font14 = self.getFont('fixedFont', 14)
        self.font18 = self.getFont('fixedFont', 18)

        self.w.tooltips = None
        #QtGui.QToolTip.setFont(self.font11)

        self.ds = Desktop.Desktop(self)
        self.ds.make_desktop(self.layout, widgetDict=self.w)
        # TEMP: FIX ME!
        self.gpmon.ds = self.ds

        for win in self.ds.toplevels:
            # add delete/destroy callbacks
            win.add_callback('closed', self.quit)
            win.set_title("Ginga")
            root = win
        self.ds.add_callback('all-closed', self.quit)

        self.w.root = root
        self.w.fscreen = None

        # Create main (center) FITS image pane
        self.w.vbox = self.w['main']
        self.w.vbox.set_spacing(0)
        self.w.mnb = self.w['channels']
        ## if isinstance(self.w.mnb, QtGui.QMdiArea):
        ##     self.w.mnb.subWindowActivated.connect(self.page_switch_mdi_cb)
        ##     self.w.mnb.set_mode('tabs')
        ## else:
        ##     self.w.mnb.currentChanged.connect(self.page_switch_cb)
        self.w.mnb.add_callback('page-switch', self.page_switch_cb)

        # readout
        if self.settings.get('share_readout', True):
            self.readout = self.build_readout()
            self.add_callback('field-info', self.readout_cb, self.readout, None)
            rw = self.readout.get_widget()
            self.w.vbox.add_widget(rw, stretch=0)

        # bottom buttons
        hbox = Widgets.HBox()
        hbox.set_border_width(0)
        hbox.set_spacing(2)

        cbox1 = Widgets.ComboBox()
        self.w.channel = cbox1
        cbox1.set_tooltip("Select a channel")
        cbox1.add_callback('activated', self.channel_select_cb)
        hbox.add_widget(cbox1, stretch=0)

        opmenu = Widgets.Menu()
        self.w.operation = opmenu
        btn = Widgets.Button("Operation")
        btn.add_callback('activated', self.invoke_op_cb)
        btn.set_tooltip("Invoke operation")
        self.w.opbtn = btn
        hbox.add_widget(btn, stretch=0)

        self.w.optray = Widgets.HBox()
        self.w.optray.set_border_width(0)
        self.w.optray.set_spacing(2)
        hbox.add_widget(self.w.optray, stretch=1)

        self.w.vbox.add_widget(hbox, stretch=0)

        # Add colormap bar
        ## cbar = self.build_colorbar()
        ## self.w.vbox.add_widget(cbar, stretch=0)

        menuholder = self.w['menu']
        self.w.menubar = self.add_menus(menuholder)

        self.add_dialogs()
        statusholder = self.w['status']
        self.add_statusbar(statusholder)

        self.w.root.show()

    def getPluginManager(self, logger, fitsview, ds, mm):
        return PluginManager.PluginManager(logger, fitsview, ds, mm)

    def _name_mangle(self, name, pfx=''):
        newname = []
        for c in name.lower():
            if not (c.isalpha() or c.isdigit() or (c == '_')):
                newname.append('_')
            else:
                newname.append(c)
        return pfx + ''.join(newname)

    def add_menus(self, holder):

        menubar = Widgets.Menubar()
        self.menubar = menubar

        # NOTE: Special hack for Mac OS X, otherwise the menus
        # do not get added to the global OS X menu
        macos_ver = platform.mac_ver()[0]
        if len(macos_ver) > 0:
            self.w['top'].add_widget(menubar_w, stretch=0)
        else:
            holder.add_widget(menubar, stretch=1)

        # create a File pulldown menu, and add it to the menu bar
        filemenu = menubar.add_name("File")

        item = filemenu.add_name("Load Image")
        item.add_callback('activated', lambda *args: self.gui_load_file())

        item = filemenu.add_name("Remove Image")
        item.add_callback("activated", lambda *args: self.remove_current_image())

        filemenu.add_separator()

        item = filemenu.add_name("Quit")
        item.add_callback('activated', lambda *args: self.windowClose())

        # create a Channel pulldown menu, and add it to the menu bar
        chmenu = menubar.add_name("Channel")

        item = chmenu.add_name("Add Channel")
        item.add_callback('activated', lambda *args: self.gui_add_channel())

        item = chmenu.add_name("Add Channels")
        item.add_callback('activated', lambda *args: self.gui_add_channels())

        item = chmenu.add_name("Delete Channel")
        item.add_callback('activated', lambda *args: self.gui_delete_channel())

        # create a Window pulldown menu, and add it to the menu bar
        wsmenu = menubar.add_name("Workspace")

        item = wsmenu.add_name("Add Workspace")
        item.add_callback('activated', lambda *args: self.gui_add_ws())

        item = wsmenu.add_name("Take Tab")
        item.add_callback('activated',
                          lambda *args: self.ds.take_tab_cb(self.w.mnb,
                                                                 args))

        ## if isinstance(self.w.mnb, QtGui.QMdiArea):
        ##     item = wsmenu.add_name("Panes as Tabs")
        ##     item.add_callback(lambda *args: self.tabstoggle_cb())
        ##     item.get_widget().setCheckable(True)
        ##     is_tabs = (self.w.mnb.get_mode() == 'tabs')
        ##     item.get_widget().setChecked(is_tabs)

        ##     item = wsmenu.add_name("Tile Panes")
        ##     item.add_callback('activated', lambda *args: self.tile_panes_cb())

        ##     item = wsmenu.add_name("Cascade Panes")
        ##     item.add_callback(lambda *args: self.cascade_panes_cb())

        # # create a Option pulldown menu, and add it to the menu bar
        # optionmenu = menubar.add_name("Option")

        # create a Plugins pulldown menu, and add it to the menu bar
        plugmenu = menubar.add_name("Plugins")
        self.w.menu_plug = plugmenu

        # create a Help pulldown menu, and add it to the menu bar
        helpmenu = menubar.add_name("Help")

        item = helpmenu.add_name("About")
        item.add_callback('activated', lambda *args: self.banner(raiseTab=True))

        item = helpmenu.add_name("Documentation")
        item.add_callback('activated', lambda *args: self.help())

        return menubar

    def add_dialogs(self):
        ## filesel = QtGui.QFileDialog(self.w.root)
        ## filesel.setFileMode(QtGui.QFileDialog.ExistingFile)
        ## filesel.setViewMode(QtGui.QFileDialog.Detail)
        ## self.filesel = filesel
        pass

    def add_plugin_menu(self, name):
        # NOTE: self.w.menu_plug is a ginga.Widgets wrapper
        item = self.w.menu_plug.add_name("Start %s" % (name))
        item.add_callback('activated',
                          lambda *args: self.start_global_plugin(name))

    def add_statusbar(self, holder):
        self.w.status = Widgets.StatusBar()
        holder.add_widget(self.w.status, stretch=1)

    def fullscreen(self):
        self.w.root.fullscreen()

    def normalsize(self):
        self.w.root.unfullscreen()

    def maximize(self):
        self.w.root.maximize()

    def toggle_fullscreen(self):
        ## if not self.w.root.isFullScreen():
        ##     self.w.root.showFullScreen()
        ## else:
        ##     self.w.root.showNormal()
        self.w.root.unfullscreen()

    def build_fullscreen(self):
        w = self.w.fscreen
        self.w.fscreen = None
        if w is not None:
            w.delete()
            return

        # Get image from current focused channel
        chinfo = self.get_channelInfo()
        fitsimage = chinfo.fitsimage
        settings = fitsimage.get_settings()
        rgbmap = fitsimage.get_rgbmap()

        root = Widgets.TopLevel()
        vbox = Widgets.VBox()
        vbox.set_border_width(0)
        vbox.set_spacing(0)
        root.add_widget(vbox, stretch=1)

        fi = self.build_viewpane(settings, rgbmap=rgbmap)
        iw = fi.get_widget()
        vbox.add_widget(iw, stretch=1)

        # Get image from current focused channel
        image = fitsimage.get_image()
        if image is None:
            return
        fi.set_image(image)

        # Copy attributes of the frame
        fitsimage.copy_attributes(fi,
                                  [#'transforms',
                                   #'cutlevels',
                                   'rgbmap'])

        root.fullscreen()
        self.w.fscreen = root

    def add_operation(self, title):
        opmenu = self.w.operation
        item = opmenu.add_name(title)
        item.add_callback('activated',
                          lambda *args: self.start_operation_cb(title))
        self.operations.append(title)

    ####################################################
    # THESE METHODS ARE CALLED FROM OTHER MODULES & OBJECTS
    ####################################################

    def make_button(self, name, wtyp, icon=None, tooltip=None):
        picon = None
        if icon:
            iconfile = os.path.join(self.iconpath, '%s.png' % icon)
            try:
                image = QImage(iconfile)
                pixmap = QPixmap.fromImage(image)
                picon = QIcon(pixmap)
                qsize = QtCore.QSize(24, 24)
            except Exception as e:
                self.logger.error("Error loading icon '%s': %s" % (
                    iconfile, str(e)))

        if wtyp == 'button':
            if picon:
                w = Widgets.Button()
                _w = w.get_widget()
                _w.setIconSize(qsize)
                _w.setIcon(picon)
            else:
                w = Widgets.Button(name)
        elif wtyp == 'toggle':
            if picon:
                w = Widgets.ToggleButton()
                _w = w.get_widget()
                _w.setIconSize(qsize)
                _w.setIcon(picon)
            else:
                w = Widgets.ToggleButton()

        return w

    def set_titlebar(self, text):
        self.w.root.set_title("Ginga: %s" % text)

    def build_readout(self):
        readout = Readout.Readout(-1, 20)
        # NOTE: Special hack for Mac OS X, otherwise the font on the readout
        # is too small
        macos_ver = platform.mac_ver()[0]
        if len(macos_ver) > 0:
            readout.set_font(self.font14)
        else:
            readout.set_font(self.font11)
        return readout

    def build_colorbar(self):
        cbar = ColorBar.ColorBar(self.logger)
        cbar.set_cmap(self.cm)
        cbar.set_imap(self.im)
        cbar.resize(700, 15)
        #cbar.show()
        self.colorbar = cbar
        self.add_callback('active-image', self.change_cbar, cbar)
        cbar.add_callback('motion', self.cbar_value_cb)

        fr = Widgets.Frame()
        fr.set_border_width(2)
        ## layout = QtGui.QHBoxLayout()
        ## fr.setLayout(layout)
        ## layout.setContentsMargins(0, 0, 0, 0)
        ## fr.setFrameStyle(QtGui.QFrame.Box | QtGui.QFrame.Raised)
        fr.set_widget(cbar)
        return fr

    def build_viewpane(self, settings, rgbmap=None):
        # instantiate bindings loaded with users preferences
        bclass = Viewers.ImageViewCanvas.bindingsClass
        bindprefs = self.prefs.createCategory('bindings')
        bd = bclass(self.logger, settings=bindprefs)

        fi = Viewers.ImageViewCanvas(logger=self.logger,
                                     rgbmap=rgbmap,
                                     settings=settings,
                                     bindings=bd)

        canvas = DrawingCanvas()
        canvas.enable_draw(False)
        fi.set_canvas(canvas)

        fi.set_follow_focus(settings.get('follow_focus', True))
        fi.enable_auto_orient(True)

        fi.add_callback('motion', self.motion_cb)
        fi.add_callback('cursor-down', self.force_focus_cb)
        fi.add_callback('key-press', self.keypress)
        fi.add_callback('drag-drop', self.dragdrop)
        fi.ui_setActive(True)

        for name in ['cuts']:
            settings.getSetting(name).add_callback('set',
                               self.change_range_cb, fi, self.colorbar)

        bd = fi.get_bindings()
        bd.enable_all(True)

        rgbmap = fi.get_rgbmap()
        rgbmap.add_callback('changed', self.rgbmap_cb, fi)
        fi.set_bg(0.2, 0.2, 0.2)
        return fi

    def add_viewer(self, name, settings,
                   use_readout=False, workspace=None):

        vbox = Widgets.VBox()
        vbox.set_border_width(1)
        vbox.set_spacing(0)

        fi = self.build_viewpane(settings)
        if hasattr(Viewers, 'GingaViewer'):
            iw = Viewers.GingaViewer(viewer=fi)
        else:
            iw = Widgets.wrap(fi.get_widget())

        fi.add_callback('focus', self.focus_cb, name)
        vbox.add_widget(iw, stretch=1)
        fi.set_name(name)

        if use_readout:
            readout = self.build_readout()
            # TEMP: hack
            readout.fitsimage = fi
            fi.add_callback('image-set', self.readout_config, readout)
            self.add_callback('field-info', self.readout_cb, readout, name)
            rw = readout.get_widget()
            ## rw.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Fixed,
            ##                                    QtGui.QSizePolicy.Fixed))
            vbox.add_widget(rw, stretch=0)
        else:
            readout = None

        # Add a page to the specified notebook
        if not workspace:
            workspace = 'channels'
        self.ds.add_tab(workspace, vbox, 1, name)

        self.update_pending()
        bnch = Bunch.Bunch(fitsimage=fi, view=iw, container=vbox,
                           readout=readout, workspace=workspace)
        return bnch


    def gui_add_channel(self, chname=None):
        if not chname:
            self.chncnt += 1
            chname = "Image%d" % self.chncnt

        captions = (('New channel name:', 'label', 'channel_name', 'entry'),
                    ('In workspace:', 'label', 'workspace', 'combobox'),
                    )

        w, b = Widgets.build_info(captions, orientation='vertical')

        # populate values
        b.channel_name.set_text(chname)
        names = self.ds.get_wsnames()
        try:
            idx = names.index(self._lastwsname)
        except:
            idx = 0
        for name in names:
            b.workspace.append_text(name)
        b.workspace.set_index(idx)

        # build dialog
        dialog = Dialog("Add Channel",
                        0,
                        [['Cancel', 0], ['Ok', 1]],
                        lambda w, rsp: self.add_channel_cb(w, rsp, b, names))

        box = dialog.get_content_area()
        box.add_widget(w, stretch=0)

        dialog.show()
        # save a handle so widgets aren't garbage collected
        self._cur_dialogs.append(dialog)

    def gui_add_channels(self):

        captions = (('Prefix:', 'label', 'Prefix', 'entry'),
                    ('Number:', 'label', 'Number', 'spinbutton'),
                    ('In workspace:', 'label', 'workspace', 'combobox'),
                    )

        w, b = Widgets.build_info(captions)
        b.prefix.set_text("Image")
        b.number.set_limits(1, 12, incr_value=1)
        b.number.set_value(1)

        cbox = b.workspace
        names = self.ds.get_wsnames()
        try:
            idx = names.index('channels')
        except:
            idx = 0
        for name in names:
            b.workspace.append_text(name)
        b.workspace.set_index(idx)

        dialog = Dialog("Add Channels",
                        0,
                        [['Cancel', 0], ['Ok', 1]],
                        lambda w, rsp: self.add_channels_cb(w, rsp, b, names))

        box = dialog.get_content_area()
        box.add_widget(w, stretch=0)

        dialog.show()
        # save a handle so widgets aren't garbage collected
        self._cur_dialogs.append(dialog)

    def gui_delete_channel(self):
        chinfo = self.get_channelInfo()
        chname = chinfo.name
        lbl = Widgets.Label("Really delete channel '%s' ?" % (chname))
        dialog = Dialog("Delete Channel",
                        0,
                        [['Cancel', 0], ['Ok', 1]],
                        lambda w, rsp: self.delete_channel_cb(w, rsp, chname))
        box = dialog.get_content_area()
        box.add_widget(lbl, stretch=0)

        dialog.show()
        # save a handle so widgets aren't garbage collected
        self._cur_dialogs.append(dialog)

    def gui_add_ws(self):

        captions = (('Workspace name:', 'label', 'Workspace name', 'entry'),
                    ('Workspace type:', 'label', 'Workspace type', 'combobox'),
                    ('In workspace:', 'label', 'workspace', 'combobox'),
                    ('Channel prefix:', 'label', 'Channel prefix', 'entry'),
                    ('Number of channels:', 'label', 'num_channels', 'spinbutton'),
                    ('Share settings:', 'label', 'Share settings', 'entry'),
                    )
        w, b = Widgets.build_info(captions)

        self.wscount += 1
        wsname = "ws%d" % (self.wscount)
        b.workspace_name.set_text(wsname)
        #b.share_settings.set_length(60)

        cbox = b.workspace_type
        cbox.append_text("Tabs")
        ## cbox.append_text("Grid")
        ## cbox.append_text("MDI")
        cbox.set_index(0)

        cbox = b.workspace
        names = self.ds.get_wsnames()
        names.insert(0, 'top level')
        try:
            idx = names.index('channels')
        except:
            idx = 0
        for name in names:
            cbox.append_text(name)
        cbox.set_index(idx)

        b.channel_prefix.set_text("Image")
        spnbtn = b.num_channels
        spnbtn.set_limits(0, 12, incr_value=1)
        spnbtn.set_value(4)

        dialog = Dialog("Add Workspace",
                        0,
                        [['Cancel', 0], ['Ok', 1]],
                        lambda w, rsp: self.new_ws_cb(w, rsp, b, names))

        box = dialog.get_content_area()
        box.add_widget(w, stretch=1)
        dialog.show()
        # save a handle so widgets aren't garbage collected
        self._cur_dialogs.append(dialog)

    def gui_load_file(self, initialdir=None):
        if self.filesel.exec_():
            fileNames = list(map(str, list(self.filesel.selectedFiles())))
            self.load_file(fileNames[0])
        #self.start_operation_cb('FBrowser')

    def statusMsg(self, format, *args):
        if not format:
            s = ''
        else:
            s = format % args

        self.w.status.set_message(s)

    def setPos(self, x, y):
        self.w.root.move(x, y)

    def setSize(self, wd, ht):
        self.w.root.resize(wd, ht)

    def setGeometry(self, geometry):
        # Painful translation of X window geometry specification
        # into correct calls to Qt
        coords = geometry.replace('+', ' +')
        coords = coords.replace('-', ' -')
        coords = coords.split()
        if 'x' in coords[0]:
            # spec includes dimensions
            dim = coords[0]
            coords = coords[1:]
        else:
            # spec is position only
            dim = None

        if dim is not None:
            # user specified dimensions
            dim = list(map(int, dim.split('x')))
            self.setSize(*dim)

        if len(coords) > 0:
            # user specified position
            coords = list(map(int, coords))
            self.setPos(*coords)


    def collapse_pane(self, side):
        """
        Toggle collapsing the left or right panes.
        """
        # TODO: this is too tied to one configuration, need to figure
        # out how to generalize this
        hsplit = self.w['hpnl']
        sizes = hsplit.sizes()
        lsize, msize, rsize = sizes
        if self._lsize is None:
            self._lsize, self._rsize = lsize, rsize
        self.logger.debug("left=%d mid=%d right=%d" % (
            lsize, msize, rsize))
        if side == 'right':
            if rsize < 10:
                # restore pane
                rsize = self._rsize
                msize -= rsize
            else:
                # minimize pane
                self._rsize = rsize
                msize += rsize
                rsize = 0
        elif side == 'left':
            if lsize < 10:
                # restore pane
                lsize = self._lsize
                msize -= lsize
            else:
                # minimize pane
                self._lsize = lsize
                msize += lsize
                lsize = 0
        #hsplit.setSizes((lsize, msize, rsize))

    def getFont(self, fontType, pointSize):
        font_family = self.settings.get(fontType)
        return GwHelp.get_font(font_family, pointSize)


    ####################################################
    # CALLBACKS
    ####################################################

    def windowClose(self, *args):
        """Quit the application.
        """
        self.quit()

    def quit(self, *args):
        """Quit the application.
        """
        self.logger.info("Attempting to shut down the application...")
        self.stop()

        root = self.w.root
        self.w.root = None
        while len(self.ds.toplevels) > 0:
            w = self.ds.toplevels.pop()
            w.delete()

    def channel_select_cb(self, index):
        if index >= 0:
            chname = self.channelNames[index]
            self.logger.debug("Channel changed, index=%d chname=%s" % (
                index, chname))
            self.change_channel(chname)

    def add_channel_cb(self, w, rsp, b, names):
        chname = str(b.channel_name.get_text())
        idx = b.workspace.get_index()
        if idx < 0:
            idx = 0
        wsname = names[idx]
        self._cur_dialogs.remove(w)
        w.delete()
        # save name for next add
        self._lastwsname = wsname
        if rsp == 0:
            return
        self.add_channel(chname, workspace=wsname)
        return True

    def add_channels_cb(self, w, rsp, b, names):
        chpfx = b.prefix.get_text()
        idx = b.workspace.get_index()
        wsname = names[idx]
        num = int(b.number.get_value())
        self._cur_dialogs.remove(w)
        w.delete()
        if (rsp == 0) or (num <= 0):
            return

        chbase = self.chncnt
        self.chncnt += num
        for i in range(num):
            chname = "%s%d" % (chpfx, chbase+i)
            self.add_channel(chname, workspace=wsname)
        return True

    def delete_channel_cb(self, w, rsp, chname):
        self._cur_dialogs.remove(w)
        w.delete()
        if rsp == 0:
            return
        self.delete_channel(chname)
        return True

    def new_ws_cb(self, w, rsp, b, names):
        try:
            wsname = str(b.workspace_name.get_text())
            idx = b.workspace_type.get_index()
            if rsp == 0:
                return
            d = { 0: 'nb', 1: 'grid', 2: 'mdi' }
            wstype = d[idx]
            idx = b.workspace.get_index()
            in_space = names[idx]

            self.add_workspace(wsname, wstype, inSpace=in_space)

            chpfx = b.channel_prefix.get_text()
            num = int(b.num_channels.get_value())
            share_list = b.share_settings.get_text().split()

            self._cur_dialogs.remove(w)
            w.delete()

            if num <= 0:
                return
        except Exception as e:
            print("Exception building workspace: %s" % (str(e)))

        # Create a settings template to copy settings from
        settings_template = self.prefs.getSettings('channel_Image')
        name = "channel_template_%f" % (time.time())
        settings = self.prefs.createCategory(name)
        settings_template.copySettings(settings)

        chbase = self.chncnt
        self.chncnt += num
        for i in range(num):
            chname = "%s%d" % (chpfx, chbase+i)
            self.add_channel(chname, workspace=wsname,
                             settings_template=settings_template,
                             settings_share=settings,
                             share_keylist=share_list)
        return True

    def invoke_op_cb(self, btn_w):
        self.logger.debug("invoking operation menu")
        menu = self.w.operation
        menu.popup(btn_w)

    def start_operation_cb(self, name):
        self.logger.debug("invoking operation menu")
        idx = self.w.channel.get_index()
        chname = str(self.w.channel.get_alpha(idx))
        return self.start_local_plugin(chname, name, None)

    ## def tile_panes_cb(self):
    ##     self.w.mnb.tileSubWindows()

    ## def cascade_panes_cb(self):
    ##     self.w.mnb.cascadeSubWindows()

    ## def tabstoggle_cb(self, useTabs):
    ##     if useTabs:
    ##         self.w.mnb.setViewMode(QtGui.QMdiArea.TabbedView)
    ##     else:
    ##         self.w.mnb.setViewMode(QtGui.QMdiArea.SubWindowView)

    def page_switch_cb(self, tab_w, index):
        self.logger.debug("index switched to %d" % (index))
        if index >= 0:
            container = tab_w.get_widget_by_index(index)
            self.logger.debug("container is %s" % (container))

            # Find the channel that contains this widget
            chnames = self.get_channelNames()
            for chname in chnames:
                chinfo = self.get_channelInfo(chname)
                if 'container' in chinfo and (chinfo.container == container):
                    fitsimage = chinfo.fitsimage
                    if fitsimage != self.getfocus_fitsimage():
                        self.logger.debug("Active channel switch to '%s'" % (
                            chname))
                        self.change_channel(chname, raisew=False)

        return True

    ## def page_switch_mdi_cb(self, w):
    ##     if w is not None:
    ##         index = self.w.mnb.indexOf(w.widget())
    ##         return self.page_switch_cb(index)


class Dialog(Widgets.TopLevel):
    def __init__(self, title=None, flags=None, buttons=None,
                 callback=None):
        super(Dialog, self).__init__(title=title)
        #self.setModal(True)

        vbox = Widgets.VBox()
        vbox.set_border_width(4)

        self.content = Widgets.VBox()
        vbox.add_widget(self.content, stretch=1)

        hbox = Widgets.HBox()

        def mklocal(val):
            def cb(widget):
                callback(self, val)
            return cb

        for name, val in buttons:
            btn = Widgets.Button(name)
            if callback:
                btn.add_callback('activated', mklocal(val))
            hbox.add_widget(btn, stretch=0)
        # add stretch
        hbox.add_widget(Widgets.Label(''), stretch=1)

        vbox.add_widget(hbox, stretch=0)

        self.set_widget(vbox)

    def get_content_area(self):
        return self.content



# END
