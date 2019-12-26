#!/usr/bin/python3

#---------------------------------------------------------------------------------------------------
import argparse
import subprocess
import logging
import json
import os
import urllib.parse
import time
from collections import OrderedDict

#---------------------------------------------------------------------------------------------------
NOK_OK = ("nok", "ok")
APP_NAME = "piot"
CONF_FILE = os.environ['HOME'] + "/." + APP_NAME + ".conf"
LOG_FILE = "/tmp/" + APP_NAME + ".log"
DB_CURRENT = "dev-current.json"

#---------------------------------------------------------------------------------------------------
log = None

#---------------------------------------------------------------------------------------------------
class Utils:
    def get_timestamp():
        return int(time.time())

    def is_dir_present(path):
        return os.path.isdir(path)

    def is_file_present(path):
        return os.path.isfile(path) 

    def is_file_empty(path):
        return os.stat(path).st_size == 0

    def split_lines(lines, prefix, cb):
        first = True
        for l in lines.splitlines():
            cb(prefix + l)
            if first:
                prefix = " " * len(prefix)
                first = False

    def log_lines(log_level, prefix, line, bid):
        def cb(line):
            log.log(log_level, line, bid, False)
        Utils.split_lines(line, prefix, cb)

    def get_db_name(device_name):
        return "db-" + device_name

    def get_file_name(device_name):
        timestamp=str(Utils.get_timestamp())
        return "dev-" + device_name + "-" + timestamp + ".json"

#---------------------------------------------------------------------------------------------------
class Logger:
    BATCH_ID_SIZE = 6
    BATCH_ID_FILLER = " " * BATCH_ID_SIZE

    def __init__(self, is_debug):
        self.bid = 0
        self.is_debug = is_debug
        self.flog = open(LOG_FILE, "w+")

    def log(self, prefix, line, bid, next_bid):
        prefix_ext = prefix + " "

        if bid == None and next_bid:
            self.bid += 1
            bid = self.bid

        if bid == None:
            prefix_ext += self.BATCH_ID_FILLER + " "
        else:
            prefix_ext += str(bid).zfill(self.BATCH_ID_SIZE) + " "

        # Write debugs to stdout only when explicitly allowed
        out = prefix_ext + line
        if prefix != "DBG" or self.is_debug:
            print(out)

        # Write all messages to log
        self.flog.write(out + "\n")
#        self.flog.flush()
        return bid

    def dbg(self, line, bid = None, next = False):
        return self.log("DBG", line, bid, next_bid=next)

    def inf(self, line, bid = None, next = False):
        return self.log("INF", line, bid, next_bid=next)

    def err(self, line, bid = None, next = False):
        return self.log("ERR", line, bid, next_bid=next)

#---------------------------------------------------------------------------------------------------
class Cmd:
    cmd = ""
    params = {}
    bid = None
    out = ""
    err = ""
    rc = 0

    def __init__(self, cmd, params):
        self.cmd = cmd
        self.params = params

        # Allocate Batch-ID 
        self.bid = self.alloc_bid()

        # Run command
        if self.is_ok():
            self.run()

        # Log status
        self.log_status()

    def alloc_bid(self):
        return None

    def run(self):
        return True

    def is_ok(self):
        return self.rc == 0

    def set_err(self, msg, rc = -1):
        self.err = msg
        self.rc = rc

    def clear_status(self):
        self.out = ""
        self.err = ""

    def log_status(self):
        log.log("DBG", "  >> rc  = " + str(self.rc), self.bid, False)
        if len(self.out) > 0:
            Utils.log_lines("DBG", "  >> out = ", self.out, self.bid)
        if len(self.err) > 0:
            Utils.log_lines("DBG", "  >> err = ", self.err, self.bid)

#---------------------------------------------------------------------------------------------------
class ShellCmd(Cmd):
    def __init__(self, cmd):
        super(ShellCmd, self).__init__(cmd, {})

    def alloc_bid(self):
        return log.dbg("Running shell command :: cmd=" + self.cmd, next=True)

    def run(self):
        ret = subprocess.run(self.cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.out = ret.stdout.decode("utf-8").strip()
        self.err = ret.stderr.decode("utf-8").strip() 
        self.rc = ret.returncode

#---------------------------------------------------------------------------------------------------
class ActionCmd(Cmd):
    def __init__(self, cmd, params):
        super(ActionCmd, self).__init__(cmd, params)

    def alloc_bid(self):
        # Test mandatory parameters
        is_ok = True
        params_str = ""
        for k, v in self.params.items():
            params_str += k + "=" + str(v) + " "
            if not v:
                is_ok = False

        # Fail if mandatory parameters are missing
        if not is_ok:
            self.set_err("Error, mandatory parameters are missing")

        # Allocate Batch-ID
        log_line = "Running action command :: cmd=" + self.cmd + " " + params_str
        log.inf(log_line)

        return log.dbg("", next=True)

#---------------------------------------------------------------------------------------------------
class ActionDbCreate(ActionCmd):
    def __init__(self, args):
        self.param_name = args.name

        super(ActionDbCreate, self).__init__(args.action, 
          OrderedDict({"name":self.param_name}))

    def run(self):
        # Get DB name
        db_name = Utils.get_db_name(self.param_name)

        # Check if DB already exists
        if Utils.is_dir_present(db_name):
            self.set_err("Error, db already exists")
            return

        # Get file name 
        db_file = Utils.get_file_name(self.param_name)

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

#---------------------------------------------------------------------------------------------------
class ActionDbWrite(ActionCmd):
    def __init__(self, args):
        self.param_name = args.name
        self.param_data = args.data

        super(ActionDbWrite, self).__init__(args.action, 
          OrderedDict({"name":self.param_name, "data":self.param_data}))

    def run(self):
        # Get DB name
        db_name = Utils.get_db_name(self.param_name)

        # Get path of current DB file
        db_file = "./" + db_name + "/" + DB_CURRENT

        # Check if DB is present
        if not Utils.is_dir_present(db_name) or not Utils.is_file_present(db_file):
            self.set_err("Error, DB is missing")
            return

        # Prefix to separate data entries
        prefix = ", "
        if Utils.is_file_empty(db_file):
            prefix = "  "

        # Build header
        timestamp = str(Utils.get_timestamp())
        header = "{\"timestamp\":" + timestamp + "}"

        # Write current file
        cmd = "echo '" + prefix + "{ "                                      + \
                    "\"header\":" + header + ","                            + \
                    "\"data\":" + self.param_data                           + \
               "}' >> " + db_file
        if not ShellCmd(cmd).is_ok():
            self.set_err("Error, failed to write data")
            return

#---------------------------------------------------------------------------------------------------
class ActionDbRead(ActionCmd):
    def __init__(self, args):
        self.param_name = args.name
        self.param_dest = args.dest
        self.param_filter = args.filter

        super(ActionDbRead, self).__init__(args.action, 
          OrderedDict({"name":self.param_name, "dest":self.param_dest, "filter":self.param_filter}))

    def run(self):
        # Get DB name
        db_name = Utils.get_db_name(self.param_name)

        # Get path of current DB file
        cur_file = "./" + db_name + "/" + DB_CURRENT

        # Check if DB is present
        if not Utils.is_dir_present(db_name) or not Utils.is_file_present(cur_file):
            self.set_err("Error, DB is missing")
            return

        # Read DB
        cmd = "(echo ["                                          + " && " + \
               "cat " + cur_file                                 + " && " + \
               "echo ]) > " + self.param_dest
        if not ShellCmd(cmd).is_ok():
            self.set_err("Error, failed to read data")
            return 

        # Apply JQ filter
        cmd = ShellCmd("cat " + self.param_dest + " | jq " + self.param_filter)
        if not cmd.is_ok():
            self.set_err("Error, failed to apply filter")
            return

        # Log JSON to stdout
        Utils.log_lines("INF", "  >> out = ", cmd.out, None)

#---------------------------------------------------------------------------------------------------
class App:
    args = None

    def __init__(self, args):
        self.args = args

        # Set log level
        global log
        log = Logger(self.args.debug)

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
            if Utils.is_dir_present(db_name):
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
        return not err;

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
#            self.action_db_write(self.args)
            ActionDbWrite(self.args)

        elif self.args.action == "db-read":
#            self.action_db_read(self.args)
            ActionDbRead(self.args)

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
    parser.add_argument('--time-begin', action='store', default=0, help='Beginning of selection timeframe')
    parser.add_argument('--time-end', action='store', default=0, help='End of selection timeframe')
    parser.add_argument('--debug', action='store_true', help='Enable debugs')

    app = App(parser.parse_args())
    app.run()
