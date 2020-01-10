#!/usr/bin/python3

#---------------------------------------------------------------------------------------------------
import argparse
import subprocess
import logging
import json
import os
import time
import sys
import socket
import urllib.parse
from collections import OrderedDict

#---------------------------------------------------------------------------------------------------
APP_NAME = "piot"
CONF_FILE = os.environ['HOME'] + "/." + APP_NAME + ".conf"
LOG_FILE = "/tmp/" + APP_NAME + ".log"
TMP_FILE = "/tmp/" + APP_NAME + "." + str(os.getpid()) + ".tmp"
DB_CURRENT = "dev-current.json"
HTTP_SERVER = False

#---------------------------------------------------------------------------------------------------
class Sensor(OrderedDict):
    def __init__(self):
        super(Sensor, self).__init__()
        self.header()

    def header(self):
        if "header" not in self:
            self["header"] = OrderedDict({                      \
                "hostname"      : Utils.get_hostname(),         \
                "uptime"        : Utils.get_uptime(),           \
                "timestamp"     : Utils.get_timestamp()})
        return self["header"]

    def data(self):
        if "data" not in self:
            self["data"] = OrderedDict()
        return self["data"]

#---------------------------------------------------------------------------------------------------
class Status(OrderedDict):
    def __init__(self):
        super(Status, self).__init__({})

    def set_action(self, action):
        self["action"] = action
        return self

    def set_param(self, name, value):
        if "params" not in self:
            self["params"] = OrderedDict({})
        self["params"][name] = value
        return self

    def set_success(self, success):
        self["success"] = success
        return self

    def set_out(self, out):
        if out:
            out = Utils.string_to_json(out)
        self["out"] = {} if not out else out
        return self

    def set_message(self, message):
        self["message"] = message
        return self

    def to_string(self):
        return Utils.json_to_string(self)

#---------------------------------------------------------------------------------------------------
class Utils:
    def get_timestamp():
        return int(time.time())

    def get_time_str(fmt = "%Y/%m/%d-%H:%M:%S"):
        return time.strftime(fmt, time.gmtime())

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
        return Utils.string_to_json(str) != None

    def read_file(path):
        body = None
        try:
            f = open(path, "r")
            if f and f.mode == "r":
                body = f.read()
        except:
            pass
        return body

    def json_to_string(json_obj):
        try:
            return str(json.dumps(json_obj))
        except:
            return "{}"

    def string_to_json(str):
        try:
            return json.loads(str)
        except:
            return None

    def get_hostname():
        return socket.gethostname()

    def get_uptime():
        with open('/proc/uptime', 'r') as f:
            sec = float(f.readline().split()[0])
        return int(sec)

#---------------------------------------------------------------------------------------------------
class Writer:
    def __init__(self, stream):
        self.stream = stream

    def write(self, str, do_flush=True, new_line=True):
        if not self.stream:
            return
        if new_line:
            str += "\n"
        self.stream.write(str)
        if do_flush:
            self.stream.flush()

#---------------------------------------------------------------------------------------------------
class Logger(Writer):
    BATCH_ID_SIZE = 6
    BATCH_ID_FILLER = " " * BATCH_ID_SIZE

    def __init__(self, dest):
        self.bid = 0
        stream = None
        if dest == "stdout":
            stream = sys.stdout
        else:
            try:
                stream = open(LOG_FILE, "w+")
            except:
                pass
        super(Logger, self).__init__(stream)

    def next_bid(self):
        self.bid += 1
        return self.bid

    def log(self, prefix, line, bid, next_bid):
        prefix_ext = prefix + " "

        if bid == None and next_bid:
            bid = self.next_bid()

        if bid == None:
            prefix_ext += Logger.BATCH_ID_FILLER + " "
        else:
            prefix_ext += str(bid).zfill(Logger.BATCH_ID_SIZE) + " "

        # Write all messages to log
        self.write(prefix_ext + line, False)
        return bid

    def dbg(self, line, bid = None, next = False):
        return self.log("DBG", line, bid, next_bid=next)

    def inf(self, line, bid = None, next = False):
        return self.log("INF", line, bid, next_bid=next)

    def err(self, line, bid = None, next = False):
        return self.log("ERR", line, bid, next_bid=next)

#---------------------------------------------------------------------------------------------------
class Cmd:
    def __init__(self, cmd, params):
        self.cmd = cmd
        self.params = params
        self.out = ""
        self.err = ""
        self.rc = 0
        self.bid = None

        # Prepare command 
        self.bid = self.prepare()

        # Run commandsete
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

    def set_err(self, err, rc = -1):
        self.err = err if err else "Generic error"
        self.rc = rc

    def set_out(self, out):
        self.out = out

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
        self.out_json = {}
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

        # Return db + file tuple
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
        return log.log("DBG", "Running action :: " + Utils.json_to_string(self.status), self.bid, True)

    def finalize(self):
        self.status.set_success(self.is_ok())
        if self.err:
            self.status.set_message(self.err)
        self.status.set_out(self.out)

        # Dump status JSON to stdout
        if not HTTP_SERVER:
            out.write(self.status.to_string(), do_flush=False)

#---------------------------------------------------------------------------------------------------
class ActionDbCreate(ActionCmd):
    def __init__(self, name):
        self.param_name = name

        super(ActionDbCreate, self).__init__("db-create", 
          OrderedDict({"name":name}))

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
    def __init__(self, name, data):
        self.param_name = name
        self.param_data = data

        super(ActionDbWrite, self).__init__("db-write", 
          OrderedDict({"name":name, "data":data}))

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

        super(ActionDbRead, self).__init__("db-read", 
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

        # Save output as array of objects
        if cmd.out[0] == '{':
            self.set_out("[" + cmd.out + "]")
        else:
            self.set_out(cmd.out)

#---------------------------------------------------------------------------------------------------
class ActionSensor(ActionCmd):
    def __init__(self, name, type, params):
        super(ActionSensor, self).__init__(name, params)

#---------------------------------------------------------------------------------------------------
class ActionSensorTemperature(ActionSensor):
    def __init__(self, name, params):
        super(ActionSensorTemperature, self).__init__(name, "temperature", params)

    def BuildSensorData(self, id, value, message):
        sensor = Sensor()
        d = sensor.data()
        d["type"] = "temperature"
        d["id"] = id
        d["value"] = value
        if message:
            d["message"] = message
        return sensor

#---------------------------------------------------------------------------------------------------
class ActionSensorDs18b20(ActionSensorTemperature):
    DS18B20_PATH = "/sys/bus/w1/devices"
    DS18B20_DATA = "w1_slave"

    def __init__(self, id):
        self.param_id = id
        super(ActionSensorDs18b20, self).__init__("sensor-ds18b20",
          OrderedDict({"id":id}))

    def run(self):
        value = -42
        msg = None
        while True:
            # Load modules
            if not ShellCmd("modprobe w1-gpio && sudo modprobe w1-therm").is_ok():
                msg = "Error, failed to load sensor modules"
                break

            # Read sensor data
            value_raw = Utils.read_file( \
              self.DS18B20_PATH + "/" + str(self.param_id) + "/" + self.DS18B20_DATA)
            if not value_raw:
                msg = "Error, failed to read sensor value"
                break

            value = value_raw / 1000
            break

        # Save sensor data
        sensor = self.BuildSensorData(str(self.param_id), value, msg)
        self.set_out(Utils.json_to_string(sensor))

        if msg:
            log.err(msg)

#---------------------------------------------------------------------------------------------------
class ActionError(ActionCmd):
    def __init__(self, args):
        self.args = args
        super(ActionError, self).__init__("error", {})

    def run(self):
        self.set_out(self.args)
        self.set_err("Error, generic fail")

#---------------------------------------------------------------------------------------------------
class ActionHttpServer(ActionCmd):
    def __init__(self, port):
        self.param_port = port

        super(ActionHttpServer, self).__init__("http-server", 
          OrderedDict({"port":self.param_port}))

    def run(self):
        from flask import Flask, jsonify, make_response
        from flask_restful import Api, Resource, request

        class RestApi(Resource):
            def get(self):
                return self.send_response(ActionError("RestApi::get"))

            def post(self):
                return self.send_response(RunAction(request.get_json()))

            def put(self):
                return self.send_response(ActionError("RestApi::put"))

            def delete(self):
                return self.send_response(ActionError("RestApi::delete"))

            def send_response(self, action):
                return make_response(jsonify(action.status), \
                    200 if action.is_ok() else 400)

        app = Flask(APP_NAME)
        api = Api(app)

        api.add_resource(RestApi, "/api")
        app.run(debug=False, port=self.param_port)

#---------------------------------------------------------------------------------------------------
class ActionHttpClient(ActionCmd):
    def __init__(self, server, auth_token, data):
        self.param_server = server
        self.param_auth_token = auth_token
        self.param_data = data

        super(ActionHttpClient, self).__init__("http-client", 
            OrderedDict({"server":server, "auth_token":auth_token, "data":data}))

    def run(self):
        # Parse data to json
        if not Utils.is_valid_json_string(self.param_data):
            return self.set_err("Error, failed to parse data")

        # Upload json to server
        cmd_str = "curl -X POST -s " + self.param_server + "/api"               + \
                              " -H \"Content-Type: application/json\""          + \
                              " -d '" + self.param_data + "'"
        cmd = ShellCmd(cmd_str)
        if not cmd.is_ok():
            return self.set_err("Error, failed to upload data to server")

        # Check if server responded with valid json
        resp_json = Utils.string_to_json(cmd.out)
        if not resp_json or "success" not in resp_json or "out" not in resp_json: 
            return self.set_err("Error, bad server response")

        # Check if server succeed
        if not resp_json["success"]: 
            return self.set_err("Error, server failed")

        # Inherit output from response
        self.set_out(Utils.json_to_string(resp_json["out"]))

#---------------------------------------------------------------------------------------------------
def RunAction(params):
    action = params.get("action")
    if action == "db-create": 
        return ActionDbCreate(params.get("name"))

    elif action == "db-write":
        # NOTE: DATA is STRING when invoking from CLI 
        #       DATA is JSON when invoking from HTTP-SERVER
        data = params.get("data")
        data_str = Utils.json_to_string(data) if isinstance(data, dict) else data
        return ActionDbWrite(params.get("name"), data_str)

    elif action == "db-read": 
        return ActionDbRead(params.get("name"), params.get("filter"))

    elif action == "sensor-ds18b20":
        return ActionSensorDs18b20(params.get("id"))

    elif action == "http-server":
        return ActionHttpServer(params.get("port"))

    elif action == "http-client":
        return ActionHttpClient(params.get("server"), params.get("auth_token"), params.get("data"))

    elif action == "http-client-sensor-ds18b20":
        # Read sensor
        params["action"] = "sensor-ds18b20"
        sensor_action = RunAction(params)
        if not sensor_action.is_ok():
            return sensor_action

        # Parse json
        if not Utils.is_valid_json_string(sensor_action.out):
             return sensor_action

        # Run HTTP client
        params["action"] = "http-client"
        params["data"] = Utils.json_to_string({"action":"db-write", "name":params.get("name"), "data": sensor_action.out})
        return RunAction(params)

    elif action == "http-client-db-read":
        # Run HTTP client
        params["action"] = "http-client"
        params["data"] = Utils.json_to_string({"action":"db-read", "name":params.get("name"), "filter": params.get("filter")})
        return RunAction(params)

    else: 
        return ActionError(Utils.json_to_string(params))

#---------------------------------------------------------------------------------------------------
"""
Fucking main
"""
if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description='Piot tool')
    parser.add_argument('--action', action='store', help='Action')
    parser.add_argument('--name', action='store', help='Name of the db')
    parser.add_argument('--id', action='store', help='ID of the sensor')
    parser.add_argument('--data', action='store', help='Data of the sensor')
    parser.add_argument('--filter', action='store', default=".", help='JQ filter')
    parser.add_argument('--auth-token', action='store', help='Authentication token')
    parser.add_argument('--server', action='store', help='Adress of the server (e.g. http://localhost:8888)')
    parser.add_argument('--port', action='store', default=8888, help='Listening port of the server')
    args = parser.parse_args()

    # Special handling when http-server
    HTTP_SERVER = args.action == "http-server"

    # Log writer
    log = Logger("stdout" if HTTP_SERVER else LOG_FILE)
    log.dbg(">" * 80)
    log.dbg("Starting " + APP_NAME + " @ " + str(Utils.get_timestamp()))

    # Stdout writer
    out = Writer(sys.stdout)

    # Run actions
    action = RunAction(vars(args))
    sys.exit(action.rc)
