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
from logging.handlers import TimedRotatingFileHandler
import tomlkit
import shutil

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
                                    logger.info("Linux Kernel Update Failed!")
                                    return False
                    else:
                        logger.error("Failed to get Response Code!")
                        logger.error(response.text)
                        return False
                else:
                    logger.info("Update Check Not Required!")
                    return False
            else:
                logger.info("No Cache File Preset at the Moment!")
                if not os.path.exists(cache_update):
                    last_update_check = datetime.datetime.now().strftime("%Y-%m-%d")
                    with open(cache_update, mode="w", encoding="utf-8") as f:
                        f.write("%s\n" % last_update_check)
                    permissions(cache_dir)
    except Exception as e:
        logger.error("Found error in get_latest_kernel_updates() %s" % e)
        return True

def get_cache_last_modified():
    try:
        if os.path.exists(cache_file):
            timestamp = datetime.datetime.fromtimestamp(pathlib.Path(cache_file).stat().st_mtime, tz=datetime.timezone.utc)
            return "%s %s" %(timestamp.date(), str(timestamp.time()).split(".")[0])
        else:
            return "Cache File Does not Exist!"
    except Exception as e:
        logger.error("Found Error in get_cache_last_modified() %s" % e)

try:
    if not os.path.exists(log_dir):
        makedirs(log_dir)
except Exception as e:
    logger.error("Found Error while creating log_dir %s" % e)

tfh = TimedRotatingFileHandler(event_log_file, encoding="utf-8", delay=False, when="W4")
tfh.setFormatter(formatter)
logger.addHandler(tfh)

def setup_config(self):
    try:
        if not os.path.exists(config_dir):
            makedirs(config_dir)
        if not os.path.exists(config_file):
            # makedirs(config_file)
            shutil.copy(config_file_default, config_dir)
            permissions(config_dir)
        return read_config(self)
    except Exception as e:
        logger.error("Found error in setup_config() %s" % e)

def update_config(config_data, bootloader):
    try:
        logger.info("Update Configuration Data...")
        with open(config_file, "w") as f:
            tomlkit.dump(config_data, f)
        return True
    except Exception as e:
        logger.error("Found error in update_config() %s" % e)

def read_config(self):
    try:
        logger.info("Reading config file: %s" %config_file)
        config_data = None
        with open(config_file, "rb") as f:
            config_data = tomlkit.load(f)
            if (config_data.get("kernels") and "official" in config_data["kernels"] is not None):
                for i in config_data["kernels"]["official"]:
                    supported_kernel_dict[i["name"]] = (i["description"], i["headers"])
            if (config_data.get("kernels") and "community" in config_data["kernels"] is not None):
                for j in config_data["kernels"]["community"]:
                    community_kernels_dict[j["name"]] = (j["description"], j["headers"], j["repository"])
            if (config_data.get("logging") is not None and "loglevel" in config_data["logging"] is not None):
                loglevel = config_data["logging"]["loglevel"].lower()
                logger.info("Setting loglevel: %s" % loglevel)
                if loglevel == "debug":
                    logger.setLevel(logging.DEBUG)
                elif loglevel == "info":
                    logger.setLevel(logging.INFO)
                else:
                    logger.warning("Invalid loglevel found! Available: Info/Debug")
                    logger.setLevel(logging.INFO)
            else:
                logger.setLevel(logging.INFO)
        return config_data
    except Exception as e:
        logger.error("Found error in read_config() %s" % e)
        sys.exit(1)

def create_cache_dir():
    try:
        if not os.path.exists(cache_dir):
            makedirs(cache_dir)
        logger.info("Cache Directory: %s" % cache_dir)
        permissions(cache_dir)
    except Exception as e:
        logger.error("Found error in create_cache_dir() %s" %e)

def create_log_dir():
    try:
        if not os.path.exists(log_dir):
            makedirs(log_dir)
        logger.info("Log Directory: %s" % log_dir)
    except Exception as e:
        logger.error("Found error in create_log_dir() %s" %e)

def install_archive_kernel(self):
    try:
        logger.debug("Cleaning pacman cache and removing official packages...")
        if os.path.exists(pacman_cache):
            for root, dirs, files in os.walk(pacman_cache):
                for name in files:
                    for official_kernels in supported_kernel_dict.keys():
                        if name.startswith(official_kernels):
                            if os.path.exists(os.path.join(root, name)):
                                os.remove(os.path.join(root, name))

        install_cmd_str = ["pacman", "-U", self.official_kernels[0], self.official_kernels[1], "--noconfirm", "--needed"]
        # Need to wait for process
        wait_for_pacman_process()

        if logger.getEffectiveLevel() == 10:
            logger.debug("Running %s" % install_cmd_str)
        event = "%s [INFO] Running %s\n" %(datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S"), " ".join(install_cmd_str))
        error = False
        self.messages_queue.put(event)
        with subprocess.Popen(install_cmd_str, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,env=locale_env) as process:
            while True:
                if process.poll() is not None:
                    break
                for line in process.stdout:
                    if logger.getEffectiveLevel() == 10:
                        print(line.strip())
                    self.messages_queue.put(line)
                    if "no space left on device" in line.lower().strip():
                        self.restore_kernel = None
                        error = True
                        break
                    if "initcpio" in line.lower().strip():
                        if "image generation successfull" in line.lower().strip():
                            error = False
                            break
                    if ("installation finished, no error reported" in line.lower().strip()):
                        error = False
                        break
                    if "error" in line.lower().strip() or "errors" in line.lower().strip():
                        error = True
                        break
        if error is True:
            self.errors_found = True
            error = True
            GLib.idle_add(
                show_mw, 
                self, 
                "System changes", 
                f"kernel {self.action} failed!\n"
                f"<b>There have been errors, please review the log</b>",
                priority=GLib.PRIORITY_DEFAULT,
                )

def wait_for_pacman_process():  