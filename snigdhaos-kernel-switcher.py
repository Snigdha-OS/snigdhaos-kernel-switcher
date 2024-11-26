#!/usr/bin/python
import os
import libs.functions as fn
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
        default_context = GLib.