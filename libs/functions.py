#!/bin/python

import os
from os import makedirs
import logging
import locale
import datetime
from datetime import timedelta
import sys
import psutil
import subprocess
import distro
import requests
import threading
from threading import Thread
import pathlib
from logging.handlers import TimedRotatingFileHandler
import tomlkit
import shutil
import time
import re
from libs.Kernel import Kernel, InstalledKernel, CommunityKernel
from ui.MessageWindow import MessageWindow
from queue import Queue
import gi
gi.require_version("Gtk", "3.0") # GTK 2.0 is dead!
from gi.repository import GLib



base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

lastest_archlinux_package_search_url = ("https://archlinux.org/packages/search/json?name=${PACKAGE_NAME}")
archlinux_mirror_archive_url = "https://archive.archlinux.org/"

headers = {
    "Content-Type": "text/plain;charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Linux x86_64) Gecko Firefox",
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
                logger.info("No Cache File Present at the Moment!")
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
        if check_kernel_installed(self.kernel.name + "-headers") and error is False:
            self.kernel_state_queue.put(0, "install")
        else:
            self.kernel_state_queue.put(1, "install")
            self.errors_found = True
            self.messages_queue.put(event)
        if check_kernel_installed(self.kernel.name) and error is False:
            self.kernel_state_queue.put(0, "install")
        else:
            self.kernel_state_queue.put(1, "install")
            self.errors_found = True
        self.kernel_state_queue.put(None)
    except Exception as e:
        logger.error("Found error in install_archive_kernel %s" %e)

    finally:
        if os.path.exists(self.lockfile):
            os.unlink(self.lockfile)

def check_kernel_installed(name):
    try:
        logger.info("Checking kernel package %s is installed!" %name)
        check_cmd_str = ["pacman", "-Q", name]
        if logger.getEffectiveLevel() == 10:
            logger.debug("Running Command: %s" % check_cmd_str)
        
        process_kernel_query = subprocess.Popen(check_cmd_str, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,env=locale_env)
        out, err = process_kernel_query.communicate(timeout=process_timeout)
        if process_kernel_query.returncode == 0:
            for line in out.decode("utf-8").splitlines():
                if line.split(" ")[0] == name:
                    logger.info("Kernel Installed")
                    return True
        else:
            logger.info("Kernel is not installed")
            return False
    except Exception as e:
        logger.error("Found error in check_kernel_installed() %s" % e)

def wait_for_pacman_process():
    logger.info("Waiting For Pacman Process")
    timeout = 120
    i = 0
    # need to check pacman lockfile
    while check_pacman_lockfile():
        time.sleep(0.1)
        if logger.getEffectiveLevel() == 10:
            logger.debug("Wait till pacman is locked!")
        i += 1
        if i == timeout:
            logger.info("Timeout!")
            break

def check_pacman_lockfile():
    return os.path.exists(pacman_lockfile)

def read_cache(self):
    try:
        self.timestamp = None
        with open(cache_file, "rb") as f:
            data = tomlkit.load(f)
            if len(data) == 0:
                logger.error("%s is empty! delete it and restart the application" %cache_file)
            name = None
            headers = None
            version = None
            size = None
            last_modified = None
            file_format = None
            if len(data) > 0:
                self.timestamp = data["timestamp"]
                self.cache_timestamp = data["timestamp"]
                if self.timestamp:
                    self.timestamp = datetime.datetime.strptime(self.timestamp, "%Y-%m-%d %H-%M-%S")
                    delta = datetime.datetime.now() - self.timestamp
                    if delta.days >= cache_days:
                        logger.info("Cache is older than 5 days! Refreshing...")
                        refresh_cache(self)
                    else:
                        if delta.days > 0:
                            logger.debug("Cache age: %s days." %delta.days)
                        else:
                            logger.debug("Cache is newer than 5 days!")
                        kernels = data["kernel"]
                        if len(kernels) > 1:
                            for i in kernels:
                                if (datetime.datetime.now().year - datetime.datetime.strptime(i["last_modified"], "%d-%b-%Y %H:%M").year <= 2):
                                    cached_kernel_list.append(Kernel(i["name"],i["headers"],i["version"],i["size"],i["last_modified"],i["file_format"]))
                            name = None
                            headers = None
                            version = None
                            size = None
                            last_modified = None
                            file_format = None

                            if len(cached_kernel_list) > 0:
                                sorted(cached_kernel_list)
                                logger.info("Kernel Cached Data has been processed!")
                        else:
                            logger.error("Cached File is Invalid! delete it and try again...")
            else:
                logger.error("Failed to read cache file!")
    except Exception as e:
        logger.error("Found error in read_cache() %s" %e)

def get_latest_versions(self):
    logger.info("Fetching Latest Kernel Information")
    kernel_versions = {}
    try:
        for i in supported_kernel_dict:
            check_cmd_str = ["pacman", "-Si", i]
            with subprocess.Popen(check_cmd_str, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,bufsize=1,universal_newlines=True,env=locale_env) as process:
                while True:
                    if process.poll() is not None:
                        break
                    for line in process.stdout:
                        if line.strip().replace(" ", "").startswith("Version:"):
                            kernel_versions[i] = (line.strip().replace(" ", "").split("Version:")[1])
                            break
        self.kernel_version_queue.put(kernel_versions)
    except Exception as e:
        logger.error("Found error in get_latest_versions() %s" %e)

def parse_archive_html(response, linux_kernel):
    for line in response.splitlines():
        if "<a href=" in line.strip():
            files = re.findall('<a href="([^"]*)', line.strip())
            if len(files) > 0:
                if "-x86_64" in files[0]:
                    version = files[0].split("-x86_64")[0]
                    file_format = files[04].split("-x86_64")[1]
                    url = ("/packages/l/%s" % archlinux_mirror_archive_url + "/%s" % linux_kernel + "/%s" % files[0]) #URL Struct unknown to me!
                    if ".sig" not in file_format:
                        if len(line.rstrip().split("    ")) > 0:
                            size = line.strip().split("     ").pop().strip()
                        last_modified = line.strip().split("</a>").pop()
                        for i in last_modified.split("    "):
                            if len(i.strip()) > 0 and ":" in i.strip():
                                last_modified = i.strip()
                        
                        headers = "%s%s" %(supported_kernel_dict[linux_kernel][1], version.replace(linux_kernel, ""))
                        if (version is not None and url is not None and headers is not None and file_format == ".pkg.tar.zst" and datetime.datetime.now().year - datetime.datetime.strptime(last_modified, "%d-%b-%Y %H:%M").year <= 2):
                            ke = Kernel(linux_kernel,headers,version,size,last_modified,file_format)
                            fetched_kernels_dict[version] = ke
                version = None
                file_format = None
                url = None
                size = None
                last_modified = None

def wait_for_response(response_queue):
    while True:
        items = response_queue.get()
        if items is None:
            break
        if len(supported_kernel_dict) == len(items):
            break

def get_response(session, linux_kernel, response_queue, response_content):
    response = session.get("%s/packages/l/%s" %(archlinux_mirror_archive_url, linux_kernel), headers=headers, allow_redirects=True, timout=60, stream=True)
    if response.status_code == 200:
        if logger.getEffectiveLevel() == 10:
            logger.debug("Response Code for %s/packages/l/%s = 200 (OK)" %(archlinux_mirror_archive_url, linux_kernel))
        if response.text is not None:
            response_content[linux_kernel] = response.text
            response_queue.put(response_content)
    else:
        logger.error("Failed To Process Request! Someting Went Wrong!")
        logger.error(response.text)
        response_queue.put(None)

def get_official_kernels(self):
    try:
        if not os.path.exists(cache_file) or self.refresh_cache is True:
            session = requests.session()
            response_queue = Queue()
            response_content = {}
            for linux_kernel in supported_kernel_dict:
                logger.info("Fetching data: %s/packages/l/%s" %(archlinux_mirror_archive_url, linux_kernel))
                Thread(target=get_response, args=(session,linux_kernel,response_queue,response_content), daemon=True).start()
            wait_for_response(response_queue)
            session.close()
            for kernel in response_content:
                parse_archive_html(response_content[kernel], kernel)
            if len(fetched_kernels_dict) > 0:
                write_cache()
                read_cache()
                self.queue_kernels.put(cached_kernel_list)
            else:
                logger.error("Failed to fetch Kernel List!")
                self.queue_kernels.put(None)
        else:
            logger.debug("Reading Cache File: %s" % cache_file)
            read_cache(self)
            self.queue_kernels.put(cached_kernel_list)
    except Exception as e:
        logger.error("Found error in get_official_kernels() %s" %e)

def wait_for_cache(self):
    while True:
        if not os.path.exists(cache_file):
            time.sleep(0.2)
        else:
            read_cache(self)
            break

def is_thread_alive(thread_name):
    for thead in threading.enumerate():
        if thead.name == thread_name and thead.is_alive():
            return True
    return False

def print_all_threads():
    for thread in threading.enumerate():
        if logger.getEffectiveLevel() == 10:
            logger.debug("Thread: %s and State: %s" %(thread.name, thread.is_alive()))

def update_progress_textview(self, line):
    try:
        if len(line) > 0:
            self.textbuffer.insert_markup()

