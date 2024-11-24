#!/bin/python

import os
from os import makedirs
import logging
import locale
import datetime
import sys
import psutil
import subprocess
import distro
import requests
import threading
import pathlib
import queue

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
def permissions(dst):
    try:
        groups = subprocess.run(["sh", "-c", "id" + sudo_username], shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=locale_env)
        for i in groups.stdout.decode().split(" "):
            if "gid" in i:
                g = i.split("(")[1]
                group = g.replace(")", "").strip()
        subprocess.call(["chown", "-R", sudo_username, + ":" + group, dst], shell=False, env=locale_env)
    except Exception as e:
        logger.error("Found Error in permissions()!" % e)

def refresh_cache(self):
    cached_kernel_list.clear()
    if os.path.exists(cache_file):
        os.remove(cache_file)

def write_cache():
    try:
        if len(fetched_kernels_dict) > 0:
            with open(cache_file,"w",encoding="utf-8") as f:
                f.write('title = "Arch Linux Kernels"\n\n')
                f.write('timestamp = "%s"\n' % datetime.datetime.now().strftime("%Y-%m-%d %H-%M-%S"))
                f.write('source = "%s"\n\n' % archlinux_mirror_archive_url)
                for kernel in fetched_kernels_dict.values():
                    f.write("[[kernel]]\n")
                    f.write('name = "%s"\nheaders = "%s"\nsize = "%s"\nfile_format = "%s"\nlast_modified = "%s"\n\n' % (kernel.name, kernel.headers, kernel.version, kernel.size, kernel.file_format,kernel.last_modified))
            permissions(cache_file)
    except Exception as e:
        logger.error("Found error in write_cache() %s" % e)

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
                permissions(cache_dir)
            else:
                with open(cache_update, mode="r", encoding="utf-8") as f:
                    last_update_check = f.read().strip()
                with open(cache_update, mode="w", encoding="utf-8") as f:
                    f.write("%s\n" % datetime.datetime.now().strftime("%Y-%m-%d"))
                permissions(cache_dir)
            logger.info("Last Update fetched on %s" % datetime.datetime.strptime(last_update_check, "%Y-%m-%d").date())
            if (datetime.datetime.strptime(last_update_check, "%Y-%m-%d").date() < datetime.datetime.now().date()):
                logger.info("Fetching Linux Package Update Date...")
                response = requests.get(lastest_archlinux_package_search_url.replace("${PACKAGE_NAME}", "linux"),headers=headers,allow_redirects=True,timeout=60,stream=True)
                if response.status_code == 200:
                    if response.json() is not None:
                        if len(response.json()["results"]) > 0:
                            if response.json()["results"][0]["last_update"]:
                                logger.info("Linux Kernel Package Last Update = %s" % datetime.datetime.strptime(response.json()["results"][0]["last_update"], "%Y-%m-%dT%H:%M:%S.%f.%z").date())
                                if (datetime.datetime.strptime(response.json()["results"][0]["last_update"], "%Y-%m-%dT%H:%M:%S.%f.%z").date()) >= (datetime.datetime.strptime(cache_timestamp, "%Y-%m-%d %H-%M-%S").date()):
                                    logger.info("Linux Package Updated!")
                                    refresh_cache(self)
                                    return True
                                else:
                                    logger.info