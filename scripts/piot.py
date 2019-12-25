#!/usr/bin/python3

#---------------------------------------------------------------------------------------------------
import argparse
import subprocess
import logging
import configparser
import json
import os
import urllib.parse
import time
from collections import OrderedDict
from time import gmtime, strftime

#---------------------------------------------------------------------------------------------------
NOK_OK=("nok", "ok")
APP_NAME = "piot"
CONF_FILE=os.environ['HOME'] + "/." + APP_NAME + ".conf"
LOG_FILE="/tmp/" + APP_NAME + ".log"
DB_CURRENT="dev-current.json"

#---------------------------------------------------------------------------------------------------
log = None
cfg = None

#---------------------------------------------------------------------------------------------------
class Config:
    def __init__(self):
        self.cfg = configparser.ConfigParser()
        self.cfg.read(CONF_FILE)

    def read(self, section, key):
        if section not in self.cfg:
            return None
        sec = self.cfg[section]

        if key not in sec:
            return None
        return sec[key]

    def write(self, section, key, value):
        if section not in self.cfg:
            self.cfg[section] = {}
        self.cfg[section][key] = value
        self.flush()

    def flush(self):
        with open(CONF_FILE, 'w+') as configfile:
            self.cfg.write(configfile)

#---------------------------------------------------------------------------------------------------
class Logger:
    BATCH_ID_SIZE = 6
    BATCH_ID_FILLER = " " * BATCH_ID_SIZE

    def __init__(self, is_debug):
        self.bid = 0
        self.is_debug = is_debug
        self.flog = open(LOG_FILE, "w+")

    def log(self, prefix, bid, msg, next_bid):
        string = prefix + " "

        if bid == None and next_bid:
            self.bid += 1
            bid = self.bid

        if bid == None:
            string += self.BATCH_ID_FILLER + " "
        else:
            string += str(bid).zfill(self.BATCH_ID_SIZE) + " "

        # Write debugs to stdout only when explicitly allowed
        out = string + msg
        if prefix != "DBG" or self.is_debug:
            print(out)

        # Write all messages to log
        self.flog.write(out + "\n")
        self.flog.flush()
        return bid

    def dbg(self, str, bid = None, next = False):
        return self.log("DBG", bid, str, next_bid = next)

    def inf(self, str, bid = None, next = False):
        return self.log("INF", bid, str, next_bid = next)

    def err(self, str, bid = None, next = False):
        return self.log("ERR", bid, str, next_bid = next)

#---------------------------------------------------------------------------------------------------
class ShellCmd:
    cmd = ""
    out = ""
    err = ""
    rc = -1

    def __init__(self, cmd):
        self.run_cmd(cmd)

    def run_cmd(self, cmd):
        self.cmd = cmd
        self.bid = log.dbg("Running shell command :: cmd=" + self.cmd, next=True)

        ret = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.out = ret.stdout.decode("utf-8").strip()
        self.err = ret.stderr.decode("utf-8").strip() 
        self.rc = ret.returncode
        self.log(self.bid)

    def log_multi_line(self, log_level, prefix_first, line, bid):
        first = True
        prefix_next = " " * len(prefix_first)
        for l in line.splitlines():
            if first:
                log.log(log_level, bid, prefix_first + l, False)
                first = False
            else:
                log.log(log_level, bid, prefix_next + l, False)

    def log(self, bid):
        log.dbg("  >> rc  = " + str(self.rc), bid=bid)
        if len(self.out) > 0:
            self.log_multi_line("DBG", "  >> out = ", self.out, bid)
        if len(self.err) > 0:
            self.log_multi_line("DBG", "  >> err = ", self.err, bid)

    def is_ok(self):
        return self.rc == 0

    def clean_status(self):
        self.out = ""
        self.err = ""

#---------------------------------------------------------------------------------------------------
class App:
    args = None

    def __init__(self, args):
        self.args = args

        # Set log level
        global log
        log = Logger(self.args.debug)

        # Read config
        global cfg
        cfg = Config()

    #-----------------------------------------------------------------------------------------------
    # ACTION
    #-----------------------------------------------------------------------------------------------
    def test_action_params(self, logline, params):
        is_ok=True
        logline += " ::"
        for k, v in params.items():
            logline += " " + k + "=" + str(v)
            if not v:
                is_ok = False
        log.inf(logline)
        if not is_ok:
            log.err("Failed, mandatory parameters missing")
        return is_ok

    #-----------------------------------------------------------------------------------------------
    def get_db_name(self, device_name):
        return "db-" + device_name

    #-----------------------------------------------------------------------------------------------
    def get_file_name(self, device_name):
        timestamp=str(int(time.time()))
        return "dev-" + device_name + "-" + timestamp + ".json"

    #-----------------------------------------------------------------------------------------------
    def action_db_create(self, a):
        if not self.test_action_params("Creating db", 
          OrderedDict({"name":a.name})):
            return False

        # Run
        err = "Error"
        while True:
            # Get DB name
            db_name = self.get_db_name(a.name)

            # Check if DB already exists
            if ShellCmd("[ -d " + db_name + " ]").is_ok():
                err += ", db already exists"
                break

            # Get file name 
            db_file = self.get_file_name(a.name)

            # Create new DB directory
            cmd = "mkdir " + db_name                                + " && " + \
                  "cd " + db_name                                   + " && " + \
                  "git init "                                       + " && " + \
                  "git checkout -b " + db_name                      + " && " + \
                  "touch " + db_file                                + " && " + \
                  "git add " + db_file                              + " && " + \
                  "ln -s " + db_file + " " + DB_CURRENT             + " && " + \
                  "git add " + DB_CURRENT                           + " && " + \
                  "git commit -m 'Initial commit'"
            if not ShellCmd(cmd).is_ok():
                err += ", failed to create DB"
                break

            # Success !!!!
            err = None 
            break

        if err:
            log.err(err);
            return False
        else:
            return True

    #-----------------------------------------------------------------------------------------------
    def action_db_write(self, a):
        if not self.test_action_params("Writing db", 
          OrderedDict({"name":a.name, "data":a.data})):
            return False

        # Run
        err = "Error"
        while True:
            # Get names
            db_name = self.get_db_name(a.name)
            cur_file = "./" + db_name + "/" + DB_CURRENT

            # Check if DB is present
            cmd = "[ -d " + db_name + " ]"                          + " && " + \
                  "[ -f " + cur_file + " ]"
            if not ShellCmd(cmd).is_ok():
                err += ", DB is missing"
                break

            # Prefix to separate data entries
            prefix = ", "
            if os.stat(cur_file).st_size == 0:
                prefix = "  "

            # Header
            timestamp = str(int(time.time()))
            header = "{\"timestamp\":\"" + timestamp + "\"" + "}"

            # Write current file
            cmd = "echo '" + prefix + "{ "                                  + \
                        "\"header\":" + header + ","                        + \
                        "\"data\":" + a.data                                + \
                   "}' >> " + cur_file

            if not ShellCmd(cmd).is_ok():
                err += ", failed to write data"
                break

            # Success !!!!
            err = None
            break

        if err:
            log.err(err);
            return False
        else:
            return True

    #-----------------------------------------------------------------------------------------------
    def action_db_read(self, a):
        if not self.test_action_params("Writing db", 
          OrderedDict({"name":a.name, "dest":a.dest, "filter":a.filter})):
            return False

        # Run
        err = "Error"
        while True:
            # Names
            db_name = self.get_db_name(a.name)

            # Current DB file
            cur_file = "./" + db_name + "/" + DB_CURRENT

            # Check if DB is present
            cmd = "[ -d " + db_name + " ]"                          + " && " + \
                  "[ -f " + cur_file + " ]"
            if not ShellCmd(cmd).is_ok():
                err += ", DB is missing"
                break

            # Write current file
            cmd = "(echo ["                                          + " && " + \
                   "cat " + cur_file                                 + " && " + \
                   "echo ]) > " + a.dest
            if not ShellCmd(cmd).is_ok():
                err += ", failed to read data"
                break

            # Apply JQ filter
            cmd = ShellCmd("cat " + a.dest + " | jq " + a.filter)
            if not cmd.is_ok():
                err += ", failed to apply filter"
                break
            cmd.log_multi_line("INF", "  >> out = ", cmd.out, None)

            # Success !!!!
            err = None
            break

        if err:
            log.err(err);
            return False
        else:
            return True

    #-----------------------------------------------------------------------------------------------
    def run(self):
        log.inf("Starting piot...")

        # Make sure that data is valid JSON
        if self.args.data:
            try:
                json_object = json.loads(self.args.data)
            except ValueError as e:
                log.err("Error, failed to parse data, not a JSON")
                return False

        # Run actions
        if self.args.action == "db-create":
            self.action_db_create(self.args)

        elif self.args.action == "db-write":
            self.action_db_write(self.args)

        elif self.args.action == "db-read":
            self.action_db_read(self.args)

#---------------------------------------------------------------------------------------------------
"""
Fucking main
"""
if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description='Piot tool')
    parser.add_argument('--action', action='store', default="show-status", help='Action to perform')
    parser.add_argument('--name', action='store', help='DB name')
    parser.add_argument('--data', action='store', help='Data in JSON format')
    parser.add_argument('--token', action='store', help='Authentication token')
    parser.add_argument('--filter', action='store', default=".", help='JQ filter')
    parser.add_argument('--limit', action='store', default=0, help='Max number of JSON entries to read')
    parser.add_argument('--dest', action='store', default="/tmp/" + str(os.getpid()), help='Destination where to read to')
    parser.add_argument('--select-start', action='store', help='Start of selection frame')
    parser.add_argument('--select-end', action='store', help='End of selection frame')
    parser.add_argument('--debug', action='store_true', help='Enable debugs')

    app = App(parser.parse_args())
    app.run()
