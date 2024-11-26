#!/bin/python
import os
import libs.functions as fn
from ui.ManagerGUI import ManagerGUI
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib, Gdk

base_dir = fn.os.path.dirname(fn.os.path.realpath(__file__))

app_name = "Snigdha OS Kernel Switcher"
app_version = "${app_version}"
app_name_dir = "snigdhaos-kernel-switcher"
app_id = "org.snigdhaos.kernelswitcher"
lock_file = "/tmp/.sks.lock"
progress_lock_file = "/tmp/.sks-progress.lock"
pid_file ="/tmp/.sks.pid" 

class Main(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=app_id, flags=Gio.ApplicationFlags.FLAGS_NONE)
    
    def do_activate(self):
        default_context = GLib.MainContext.default()
        win = self.props.active_window
        if not win:
            win = ManagerGUI(application=self, app_name=app_name, default_context=default_context,app_version=app_version)
        display = Gtk.Widget.get_display(win)
        win.set_icon_name("snigdhaos-kernel-switcher-tux")
        provider = Gtk.CssProvider.new()
        css_file = Gio.file_new_for_path(css_file)
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win.present()

    def do_startup(self):
        Gtk.Application.do_startup(self)
    
    def do_shutdown(self):
        Gtk.Application.do_shutdown(self)
        if os.path.exists(lock_file):
            os.remove(lock_file)
        if os.path.exists(pid_file):
            os.remove(pid_file)
        if os.path.exists(progress_lock_file):
            os.remove(progress_lock_file)
    
    def snigdhal_handler(sig, frame):
        Gtk.main_quit(0)
    
    # if __name__ == "__main__":
    #     try:
    #     except Exception as e:
    #         return False