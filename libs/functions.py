#!/bin/python

import os
import logging
import locale
import datetime
import sys

import gi
gi.require_version("Gtk", "3.0") # GTK 2.0 is dead!
from gi.repository import GLib

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

lastest_archlinux_package_search_url = ("https://archlinux.org/packages/search/json?name=${PACKAGE_NAME}")
archlinux_mirror_archive_url = "https://archive.archlinux.org/"

headers = {
    "Content-Type": "text/plain;charset=UTF-8",
    "User-Agent": "",
}

cache_days = 5
fetched_kernels_dict = {}
cached_kernel_list = []
community_kernels_list = []
supported_kernel_dict = {}
community_kernels_dict = {}
pacman_repos_list = []
process_timeout = 500
sudo_username = os.getlogin()
home = "/home" + str(sudo_username)

pacman_logfile = "/var/log/pacman.log"
pacman_lockfile = "/var/lib/pacman/db.lck"
pacman_conf_file = "/etc/pacman.conf"
pacman_cache = "/var/cache/pacman/pkg"

#Threads
thread_get_kernels = "thread_get_kernels"
thread_get_community_kernels = "thread_get_community_kernels"
thread_install_community_kernel = "thread_install_community_kernel"
thread_install_archive_kernel = "thread_install_archive_kernel"
thread_check_kernel_state = "thread_check_kernel_state"
thread_uninstall_kernel = "thread_uninstall_kernel"
thread_monitor_messages = "thread_monitor_messages"
thread_refresh_cache = "thread_refresh_cache"
thread_refresh_ui = "thread_refresh_ui"

cache_dir = "%s/.cache/snigdhaos-kernel-switcher" % home
cache_file = "%s/kernels.toml" % cache_dir
cache_update = "%s/update" % cache_dir

log_dir = "/var/log/snigdhaos-kernel-switcher"
event_log_file = "%s/event.log" % log_dir

config_file_default = "%s/defaults/config.toml" % base_dir
config_dir = "%s/.config/snigdhaos-kernel-switcher" % home
config_file = "%s/.config/snigdhaos-kernel-switcher/config.toml" % home

logger = logging.getLogger("logger")

# console handler
ch = logging.StreamHandler()

# Format
formatter = logging.Formatter("%(asctime)s:%(levelname)s > %(message)s", "%Y-%m-%d %H:%M:%S")
ch.setFormatter(formatter)
logger.addHandler(ch)

#Local
locale.setlocale(locale.LC_ALL, "C.utf8")
locale_env = os.environ
locale_env["LC_ALL"] = "C.utf8"

# Function -> check general update
def get_latest_kernel_updates(self):
    logger.info("Getting latest Kernel Version! Please Wait...")
    try:
        latest_update_check = None
        fetch_update = False
        check_timeout = None

        if os.path(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                data = f.readlines()[2]
                if len(data) == 0:
                    logger.error("%s is empty! Please restart the application after deleting it." %cache_file)
                if len(data) > 0 and "timestamp" in data.strip():
                    cache_timestamp = (data.split("timestamp = ")[1].replace('"', "").strip())
            if not os.path.exists(cache_update):
                last_update_check = datetime.datetime.now().strftime("%Y-%m-%d")
                with open(cache_update, mode="w", encoding="utf-8") as f:
                    f.write("%s\n" % last_update_check)
                