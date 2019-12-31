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

from flask import Flask
from flask_restful import Api, Resource, reqparse, request
from flask import jsonify, make_response

#---------------------------------------------------------------------------------------------------
APP_NAME = "piot"
CONF_FILE = os.environ['HOME'] + "/." + APP_NAME + ".conf"
LOG_FILE = "/tmp/" + APP_NAME + ".log"
TMP_FILE = "/tmp/" + APP_NAME + "." + str(os.getpid()) + ".tmp"
DB_CURRENT = "dev-current.json"

#---------------------------------------------------------------------------------------------------
class Data(Resource):
    def get(self, name):
        name = request.args.get('name', default = None, type = str)
        filter = request.args.get('filter', default = ".", type = str)

        return make_response(jsonify(ActionDbRead(name, filter).status), 200)
    def post(self, name):
        return "Not supported", 405
    def put(self, name):
        return "Not supported", 405
    def delete(self, name):
        return "Not supported", 405

#---------------------------------------------------------------------------------------------------
class Status(OrderedDict):
    def __init__(self):
        super(Status, self).__init__({})

    def set_action(self, action):
        self["action"] = action

    def set_param(self, name, value):
        if "params" not in self:
            self["params"] = OrderedDict({})
        self["params"][name] = value

    def set_success(self, success):
        self["success"] = success

    def set_out(self, out):
        if out:
            try:
                out = json.loads(out)
            except:
                out = None

        self["out"] = {} if not out else out

    def set_message(self, message):
        self["message"] = message

    def to_string(self):
        try:
            return str(json.dumps(self))
        except:
            return "{}"

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

    def del_file(path):
        return os.remove(path)

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

    def is_valid_json_string(str):
        try:
            json.loads(str)
            return True
        except:
            pass
        return False

#---------------------------------------------------------------------------------------------------
class Logger:
    BATCH_ID_SIZE = 6
    BATCH_ID_FILLER = " " * BATCH_ID_SIZE

    def __init__(self):
        self.bid = 0
        self.flog = open(LOG_FILE, "w+")

    def next_bid(self):
        self.bid += 1
        return self.bid

    def log(self, prefix, line, bid, next_bid):
        prefix_ext = prefix + " "

        if bid == None and next_bid:
            bid = self.next_bid()

        if bid == None:
            prefix_ext += self.BATCH_ID_FILLER + " "
        else:
            prefix_ext += str(bid).zfill(self.BATCH_ID_SIZE) + " "

        # Write debugs to stdout only when explicitly allowed
        out = prefix_ext + line
        if prefix != "DBG":
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

        # Prepare command 
        self.bid = self.prepare()

        # Run command
        if self.is_ok():
            self.run()

        # Finalize command
        self.finalize()

        # Write log
        log.log("DBG", "  >> rc  = " + str(self.rc), self.bid, False)
        if len(self.out) > 0:
            Utils.log_lines("DBG", "  >> out = ", self.out, self.bid)
        if len(self.err) > 0:
            Utils.log_lines("DBG", "  >> err = ", self.err, self.bid)

    def prepare(self):
        return None

    def run(self):
        return True

    def finalize(self):
        return True

    def is_ok(self):
        return self.rc == 0

    def set_err(self, msg, rc = -1):
        self.err = msg
        self.rc = rc

#---------------------------------------------------------------------------------------------------
class ShellCmd(Cmd):
    def __init__(self, cmd):
        super(ShellCmd, self).__init__(cmd, {})

    def prepare(self):
        return log.dbg("Running shell command :: cmd=" + self.cmd, next=True)

    def run(self):
        ret = subprocess.run(self.cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.out = ret.stdout.decode("utf-8").strip()
        self.err = ret.stderr.decode("utf-8").strip() 
        self.rc = ret.returncode

#---------------------------------------------------------------------------------------------------
class ActionCmd(Cmd):
    def __init__(self, cmd, params):
        self.status = Status()
        self.status.set_action(cmd)
        super(ActionCmd, self).__init__(cmd, params)

    def get_db_name(self, device_name):
        return "db-" + device_name

    def get_file_name(self, device_name):
        timestamp=str(Utils.get_timestamp())
        return "dev-" + device_name + "-" + timestamp + ".json"

    def get_db_files(self, name):
        # Get DB name
        db_name = self.get_db_name(name)
        if not Utils.is_dir_present(db_name):
            self.set_err("Error, DB dir is missing :: name=" + name)
            return None, None

        # Get path of current DB file
        db_file = "./" + db_name + "/" + DB_CURRENT
        if not Utils.is_file_present(db_file):
            self.set_err("Error, DB file is missing :: file=" + name)
            return None, None

        # Return dit + file tuple
        return db_name, db_file

    def prepare(self):
        # Test mandatory parameters
        is_ok = True
        for k, v in self.params.items():
            v_str = str(v)
            self.status.set_param(k, v_str)

            if not v:
                is_ok = False

        # Fail if mandatory parameters are missing
        if not is_ok:
            self.set_err("Error, mandatory parameters are missing")

        # Allocate Batch-ID
        return log.log("DBG", "Running action :: " + self.status.to_string(), self.bid, True)

    def finalize(self):
        self.status.set_success(self.is_ok())
        self.status.set_message("" if not self.err else self.err)
        self.status.set_out(self.out)

        # Dump status JSON to stdout
        print(self.status.to_string())

#---------------------------------------------------------------------------------------------------
class ActionDbCreate(ActionCmd):
    def __init__(self, args):
        self.param_name = args.name

        super(ActionDbCreate, self).__init__(args.action, 
          OrderedDict({"name":self.param_name}))

    def run(self):
        # Get DB name
        db_name = self.get_db_name(self.param_name)

        # Check if DB already exists
        if Utils.is_dir_present(db_name):
            return self.set_err("Error, db already exists")

        # Get file name 
        db_file = self.get_file_name(self.param_name)

        # Create new DB
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
            return self.set_err("Error, failed to create DB")

#---------------------------------------------------------------------------------------------------
class ActionDbWrite(ActionCmd):
    def __init__(self, args):
        self.param_name = args.name
        self.param_data = args.data

        super(ActionDbWrite, self).__init__(args.action, 
          OrderedDict({"name":self.param_name, "data":self.param_data}))

    def run(self):
        # Validate data
        if not Utils.is_valid_json_string(self.param_data):
            return self.set_err("Error, invalid json in data")

        # Get DB files
        db_name, db_file = self.get_db_files(self.param_name)
        if not db_name: 
            return

        # Prefix to separate data entries
        prefix = "  " if Utils.is_file_empty(db_file) else ", "

        # Build header
        timestamp = str(Utils.get_timestamp())
        header = "{\"timestamp\":" + timestamp + "}"

        # Write current file
        cmd = "echo '" + prefix + "{ "                                      + \
                    "\"header\":" + header + ","                            + \
                    "\"data\":" + self.param_data                           + \
               "}' >> " + db_file
        if not ShellCmd(cmd).is_ok():
            return self.set_err("Error, failed to write data")

#---------------------------------------------------------------------------------------------------
class ActionDbRead(ActionCmd):
    def __init__(self, name, filter):
        self.param_name = name
        self.param_filter = filter

        super(ActionDbRead, self).__init__(name, 
          OrderedDict({"name":name, "filter":filter}))

    def run(self):
        # Get DB files
        db_name, db_file = self.get_db_files(self.param_name)
        if not db_name: 
            return

        # Read DB
        cmd = "(echo ["                                          + " && " + \
               "cat " + db_file                                  + " && " + \
               "echo ]) > " + TMP_FILE
        if not ShellCmd(cmd).is_ok():
            return self.set_err("Error, failed to read data")

        # Apply JQ filter
        cmd = ShellCmd("jq --compact-output " + self.param_filter + " " + TMP_FILE)
        Utils.del_file(TMP_FILE);
        if not cmd.is_ok():
            return self.set_err("Error, failed to apply filter")

        # Save output
        self.out = cmd.out

#---------------------------------------------------------------------------------------------------
class ActionRunRest(ActionCmd):
    def __init__(self, port):
        self.param_port = port

        super(ActionRunRest, self).__init__("run-rest", 
          OrderedDict({"port":self.param_port}))

    def run(self):
        app = Flask(APP_NAME)
        api = Api(app)

        api.add_resource(Data, "/data/<string:name>")
        app.run(debug=True, port=self.param_port)

#---------------------------------------------------------------------------------------------------
"""
Fucking main
"""
if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description='Piot tool')
    parser.add_argument('--action', action='store', help='Action to perform')
    parser.add_argument('--name', action='store', help='DB name')
    parser.add_argument('--data', action='store', help='Data in JSON format')
    parser.add_argument('--token', action='store', help='Authentication token')
    parser.add_argument('--filter', action='store', default=".", help='JQ filter')
    parser.add_argument('--limit', action='store', default=0, help='Max number of JSON entries to read')
    parser.add_argument('--time-begin', action='store', default=0, help='Beginning of selection timeframe')
    parser.add_argument('--time-end', action='store', default=0, help='End of selection timeframe')
    parser.add_argument('--port', action='store', default=8888, help='Rest listening port')
    args = parser.parse_args()

    # Init globals
    global log
    log = Logger()

    # Intro
    log.dbg(">" * 80)
    log.dbg("Starting " + APP_NAME + " @ " + str(Utils.get_timestamp()))

    # Run actions
    arg = parser.parse_args()
    if args.action == "db-create":
        ActionDbCreate(args)

    elif args.action == "db-write":
        ActionDbWrite(args)

    elif args.action == "db-read":
        ActionDbRead(args.name, args.filter)

    elif args.action == "run-rest":
        ActionRunRest(args.port)
