#!/usr/bin/python3

#---------------------------------------------------------------------------------------------------
import argparse
import subprocess
import logging
import json
import os
import time
import datetime
import sys
import socket
import random
import urllib.parse
import copy
import re
from collections import OrderedDict

#---------------------------------------------------------------------------------------------------
APP_NAME = "piot"
CONF_FILE = os.environ['HOME'] + "/." + APP_NAME + ".conf"
LOG_FILE = "/tmp/" + APP_NAME + ".log"
TMP_FILE = "/tmp/" + APP_NAME + "." + str(os.getpid()) + ".tmp"
DB_CURRENT = "dev-current.json"
GLOBAL_ARGS = None
SECONDS = { "s" : 1, 
            "m" : 60, 
            "h" : 60 * 60,
            "d" : 60 * 60 * 24,
            "w" : 60 * 60 * 24 * 7,
            "M" : None,
            "y" : None}

#---------------------------------------------------------------------------------------------------
class FakeRange():
    def __init__(self, p):
        self.r_from = Utils.GetTimestampFromTimedef(p.get("range-from"))
        self.r_to = Utils.GetTimestampFromTimedef(p.get("range-to"))
        self.r_interval = p.get("range-interval")
        self.r_size = p.get("range-size")
        self.idx = 0

    def Next(self):
        if self.idx >= self.r_size:
            return None

        self.idx += 1
        return self.r_from + (self.idx - 1) * self.r_interval

#---------------------------------------------------------------------------------------------------
class Sensor(OrderedDict):
    def __init__(self):
        super(Sensor, self).__init__()
        self.Header()

    def Header(self):
        if "sens_h" not in self:
            self["sens_h"] = OrderedDict({              \
                "host"      : Utils.GetHostname(),      \
                "up"        : Utils.GetUptime(),        \
                "ts"        : Utils.GetTimestamp()})
        return self["sens_h"]

    def Data(self):
        if "sens_d" not in self:
            self["sens_d"] = OrderedDict()
        return self["sens_d"]

#---------------------------------------------------------------------------------------------------
class Status(OrderedDict):
    def __init__(self):
        super(Status, self).__init__({})

    def SetAction(self, action):
        self["action"] = action
        return self

    def SetParam(self, name, value):
        if "params" not in self:
            self["params"] = OrderedDict({})
        self["params"][name] = value
        return self

    def SetSuccess(self, success):
        self["success"] = success
        return self

    def SetOut(self, out):
        self["out"] = {} if not out else out
        return self

    def SetMessage(self, message):
        self["message"] = message
        return self

#---------------------------------------------------------------------------------------------------
class Utils:
    def StrToInt(str):
        val = 0
        try:
            val = int(str)
        except:
            pass
        return val

    def GetUnixTimestamp():
        return int(time.time())

    def GetTimestamp():
        return time.time()

    def GetTimestampFromString(val, fmt = "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            dt = datetime.datetime.strptime(val, fmt)
            ts = datetime.datetime.timestamp(dt)
            return ts
        except:
            return None

    def GetStringFromTimestamp(val, fmt = "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.datetime.fromtimestamp(val).strftime(fmt)
        except:
            return "error"

    def GetTimestampFromTimedef(timedef, now_ts = None):
        #0 - base
        #1 - offset
        #2 - offset direction
        #3 - offset value
        #4 - offset unit
        #6 - full period
        #7 - full period unit
        p = "(\w+)"                 + \
            "("                     + \
                 "(\+|\-)"          + \
                 "([0-9]+)"         + \
                 "(s|m|h|d|w|M|y)"  + \
            ")?"                    + \
            "("                     + \
                 "\/"               + \
                 "(s|m|h|d|w|M|y)"  + \
            ")?"

        # Get current time
        dt = datetime.datetime.now() if now_ts == None \
            else datetime.datetime.fromtimestamp(now_ts)

        # Go!
        ts = None
        err = None
        match = re.fullmatch(p, timedef)
        while True:
            if not match:
                err = "no match"; break

            groups = match.groups()
            if len(groups) != 7:
                err = "wrong groups" ; break

            # Base
            base = groups[0]
            if base != "now":
                err = "bad base" ; break

            # Offset
            if groups[1]:
                # Direction
                off_dir = +1 if groups[2] == "+" \
                    else -1

                # Value
                off_value = Utils.StrToInt(groups[3])

                # Unit
                off_unit = groups[4]
                if off_unit not in SECONDS:
                    err = "bad unit" ; break

                # Process time offset that is expressed in seconds (s|m|h|d|w)
                secs = SECONDS[off_unit]
                if secs:
                    delta = datetime.timedelta(seconds = off_value * secs)
                    dt = dt + delta if (off_dir > 0) \
                        else dt - delta

                # Process variable size time offset (M|y)
                else:
                    if off_unit == "M":
                        dt = dt.replace(                                    \
                            year = dt.year + off_dir * int(off_value / 12), \
                            month = dt.month + off_dir * (off_value % 12))

                    elif off_unit == "y":
                        dt = dt.replace(                                    \
                            year = dt.year + off_dir * off_value)

                    else:
                        dt = None

            # Convert datetime to timestamp
            if dt:
                ts = datetime.datetime.timestamp(dt)

            # End loop
            break

        if err:
            log.Err("Timedef parsing failed, " + err + " :: val=" + timedef)
        return ts

    def IsDirPresent(path):
        return os.path.isdir(path)

    def IsFilePresent(path):
        return os.path.isfile(path) 

    def IsFileEmpty(path):
        return os.stat(path).st_size == 0

    def DelFile(path):
        return os.remove(path)

    def SplitLines(lines, prefix, cb):
        first = True
        for l in lines.splitlines():
            cb(prefix + l)
            if first:
                prefix = " " * len(prefix)
                first = False

    def LogLines(log_level, prefix, line, bid):
        def cb(line):
            log.Log(log_level, line, bid, False)
        Utils.SplitLines(line, prefix, cb)

    def ReadFile(path):
        body = None
        try:
            f = open(path, "r")
            if f and f.mode == "r":
                body = f.read()
        except:
            pass
        return body

    def JsonToStr(json_obj):
        try:
            return str(json.dumps(json_obj))
        except:
            return "{}"

    def StrToJson(str):
        try:
            return json.loads(str)
        except:
            return None

    def GetHostname():
        return socket.gethostname()

    def GetUptime():
        with open('/proc/uptime', 'r') as f:
            sec = float(f.readline().split()[0])
        return int(sec)

#---------------------------------------------------------------------------------------------------
class Writer:
    def __init__(self, stream):
        self.stream = stream

    def Write(self, str, do_flush=True, new_line=True):
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

    def NextBid(self):
        self.bid += 1
        return self.bid

    def Log(self, prefix, line, bid, next_bid):
        prefix_ext = prefix + " "

        if bid == None and next_bid:
            bid = self.NextBid()

        if bid == None:
            prefix_ext += Logger.BATCH_ID_FILLER + " "
        else:
            prefix_ext += str(bid).zfill(Logger.BATCH_ID_SIZE) + " "

        self.Write(prefix_ext + line, False)
        return bid

    def Dbg(self, line, bid = None, next = False):
        return self.Log("DBG", line, bid, next_bid=next)

    def Inf(self, line, bid = None, next = False):
        return self.Log("INF", line, bid, next_bid=next)

    def Err(self, line, bid = None, next = False):
        return self.Log("ERR", line, bid, next_bid=next)

#---------------------------------------------------------------------------------------------------
class CmdResult:
    def __init__(self):
        self.is_json = False
        self.out = ""
        self.err = ""
        self.rc = 0

    def SetOut(self, out):
        # OrderedDict is list of key-value tuples
        self.is_json = isinstance(out, dict) or isinstance(out, list)
        self.out = out

    def SetErr(self, err="hmm... something went wrong :(", rc=42):
        self.err = err
        self.rc = rc

    def Ok(self):
        return self.rc == 0

    def Rc(self):
        return self.rc

    def IsJson(self):
        return self.is_json

    def OutStr(self):
        return self.out if not self.is_json \
                        else Utils.JsonToStr(self.out)

    def OutJson(self):
        return self.out if self.is_json \
                        else Utils.StrToJson(self.out)

    def Err(self):
        return self.err

#---------------------------------------------------------------------------------------------------
class Cmd(CmdResult):
    def __init__(self, cmd, params):
        super(Cmd, self).__init__()

        self.cmd = cmd
        self.params = params
        self.bid = None

        # Prepare command 
        self.bid = self.Prepare()

        # Run command
        if self.Ok():
            self.Run()

        # Finalize command
        self.Finalize()

        # Write log
        log.Log("DBG", "  >> rc  = " + str(self.Rc()), self.bid, False)
        out_str = self.OutStr()
        if len(out_str) > 0:
            Utils.LogLines("DBG", "  >> out = ", out_str, self.bid)
        err_str = self.Err()
        if len(err_str) > 0:
            Utils.LogLines("DBG", "  >> err = ", err_str, self.bid)

    def Prepare(self):
        return None

    def Run(self):
        return True

    def Finalize(self):
        return True

#---------------------------------------------------------------------------------------------------
class ShellCmd(Cmd):
    def __init__(self, cmd):
        super(ShellCmd, self).__init__(cmd, {})

    def Prepare(self):
        return log.Dbg("Running shell command :: cmd=" + self.cmd, next=True)

    def Run(self):
        ret = subprocess.run(self.cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.SetOut(ret.stdout.decode("utf-8").strip())
        self.SetErr(ret.stderr.decode("utf-8").strip(), ret.returncode)

#---------------------------------------------------------------------------------------------------
class ActionCmd(Cmd):
    def __init__(self, cmd, params):
        self.status = Status()
        self.status.SetAction(cmd)
        super(ActionCmd, self).__init__(cmd, params)

    def GetDbName(self, device_name):
        return "db-" + device_name

    def GetFileName(self, device_name):
        timestamp=str(Utils.GetTimestamp())
        return "dev-" + device_name + "-" + timestamp + ".json"

    def GetDbFiles(self, name):
        # Get DB name
        db_name = self.GetDbName(name)
        if not Utils.IsDirPresent(db_name):
            self.SetErr("Error, DB dir is missing :: name=" + name)
            return None, None

        # Get path of current DB file
        db_file = "./" + db_name + "/" + DB_CURRENT
        if not Utils.IsFilePresent(db_file):
            self.SetErr("Error, DB file is missing :: file=" + name)
            return None, None

        # Return db + file tuple
        return db_name, db_file

    def Prepare(self):
        # Test mandatory parameters
        is_ok = True
        for k, v in self.params.items():
            v_str = str(v)
            self.status.SetParam(k, v_str)

            if v == None:
                is_ok = False
                break

        # Fail if mandatory parameters are missing
        if not is_ok:
            self.SetErr("Error, mandatory parameters are missing")

        # Allocate Batch-ID
        bid = log.Log("DBG", "", self.bid, True)
        log.Log("DBG", "Running action :: " + Utils.JsonToStr(self.status), bid, False)
        return bid

    def Finalize(self):
        # Set success
        self.status.SetSuccess(self.Ok())

        # Set error message
        err_str = self.Err()
        if len(err_str) > 0:
            self.status.SetMessage(err_str)

        # Set output
        self.status.SetOut(self.OutJson())

#---------------------------------------------------------------------------------------------------
class ActionDbCreate(ActionCmd):
    def __init__(self, name):
        self.p_name = name
        super(ActionDbCreate, self).__init__("db-create", 
          OrderedDict({"name":name}))

    def Run(self):
        # Get DB name
        db_name = self.GetDbName(self.p_name)

        # Check if DB already exists
        if Utils.IsDirPresent(db_name):
            return self.SetErr("Error, db already exists")

        # Get file name 
        db_file = self.GetFileName(self.p_name)

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
        if not ShellCmd(cmd).Ok():
            return self.SetErr("Error, failed to create DB")

#---------------------------------------------------------------------------------------------------
class ActionDbWrite(ActionCmd):
    def __init__(self, name, data, random):
        self.p_name = name
        self.p_data = data
        self.p_random = random
        super(ActionDbWrite, self).__init__("db-write", 
          OrderedDict({"name":name, "data":data, "random":random}))

    def Run(self):
        # Get DB files
        db_name, db_file = self.GetDbFiles(self.p_name)
        if not db_name: 
            return

        # Prefix to separate data entries
        prefix = "  " if Utils.IsFileEmpty(db_file) else ", "

        # Build header
        timestamp = str(fake_range.Next()) if fake_range \
            else str(Utils.GetTimestamp())
        header = "{\"ts\":" + timestamp + "}"

        # Write current file
        cmd = "echo '" + prefix + "{ "                           + \
                    "\"db_h\":" + header + ","                   + \
                    "\"db_d\":" + Utils.JsonToStr(self.p_data)   + \
               "}' >> " + db_file
        if not ShellCmd(cmd).Ok():
            return self.SetErr("Error, failed to write data")

#---------------------------------------------------------------------------------------------------
class ActionDbRead(ActionCmd):
    def __init__(self, name, filter):
        self.p_name = name
        self.p_filter = filter
        super(ActionDbRead, self).__init__("db-read", 
          OrderedDict({"name":name, "filter":filter}))

    def Run(self):
        # Get DB files
        db_name, db_file = self.GetDbFiles(self.p_name)
        if not db_name:
            return

        # Read DB
        cmd = "(echo ["                                          + " && " + \
               "cat " + db_file                                  + " && " + \
               "echo ]) > " + TMP_FILE
        if not ShellCmd(cmd).Ok():
            return self.SetErr("Error, failed to read data")

        # Apply JQ filter
        cmd = ShellCmd("jq --compact-output " + self.p_filter + " " + TMP_FILE)
        Utils.DelFile(TMP_FILE);
        if not cmd.Ok():
            return self.SetErr("Error, failed to apply filter")

        # Save output as array of objects
        out = cmd.OutStr()
        if cmd.out[0] == '{':
            self.SetOut("[" + out + "]")
        else:
            self.SetOut(out)

#---------------------------------------------------------------------------------------------------
class ActionSensor(ActionCmd):
    def __init__(self, name, random, type, params):
        self.is_random = random
        super(ActionSensor, self).__init__(name, params)

    def IsRandom(self):
        return self.is_random

#---------------------------------------------------------------------------------------------------
class ActionSensorTemperature(ActionSensor):
    def __init__(self, name, random, params):
        super(ActionSensorTemperature, self).__init__(name, random, "temperature", params)

    def BuildSensorData(self, id, value, message):
        sensor = Sensor()
        d = sensor.Data()
        d["type"] = "temp"
        d["id"] = id
        d["val"] = value
        if message:
            d["message"] = message
        return sensor

#---------------------------------------------------------------------------------------------------
class ActionSensorDs18b20(ActionSensorTemperature):
    DS18B20_PATH = "/sys/bus/w1/devices"
    DS18B20_DATA = "w1_slave"

    def __init__(self, id, random):
        self.p_id = id
        super(ActionSensorDs18b20, self).__init__("sensor-ds18b20", random, 
          OrderedDict({"id":id}))

    def Run(self):
        value = -42
        msg = None

        if self.IsRandom():
            value = random.randrange(-10, 100)

        else:
            while True:
                # Load kernel modules
                if not ShellCmd("sudo modprobe w1-gpio && sudo modprobe w1-therm").Ok():
                    msg = "Error, failed to load sensor modules"
                    break

                # Read sensor data
                value_raw = Utils.ReadFile( \
                  self.DS18B20_PATH + "/" + str(self.p_id) + "/" + self.DS18B20_DATA)
                if not value_raw:
                    msg = "Error, failed to read sensor value"
                    break

                value = value_raw / 1000
                break

        # Save sensor data
        sensor = self.BuildSensorData(self.p_id, value, msg)
        self.SetOut(sensor)

        if msg:
            log.Err(msg)

#---------------------------------------------------------------------------------------------------
class ActionError(ActionCmd):
    def __init__(self, msg, args = None):
        self.p_msg = msg
        self.p_args = args
        super(ActionError, self).__init__("error", {})

    def Run(self):
        if self.p_args:
            self.SetOut(self.p_args)
        self.SetErr(self.p_msg)

#---------------------------------------------------------------------------------------------------
class ActionOk(ActionCmd):
    def __init__(self, msg, args = None):
        self.p_msg = msg
        self.p_args = args
        super(ActionOk, self).__init__("ok", {})

    def Run(self):
        if self.p_args:
            self.SetOut(self.p_args)

#---------------------------------------------------------------------------------------------------
class ActionHttpServer(ActionCmd):
    def __init__(self, addr, port):
        self.p_addr = addr
        self.p_port = port
        super(ActionHttpServer, self).__init__("http-server", 
          OrderedDict({"addr":self.p_addr, "port":self.p_port}))

    def Run(self):
        from flask import Flask, jsonify, make_response
        from flask_restful import Api, Resource, request

        #-------------------------------------------------------------------------------------------
        class RestApi(Resource):
            def get(self):
                self.PrepateRequest()
                return self.BuildResponse(ActionError("Error, GET not supported"))

            def post(self):
                json = self.PrepateRequest()

                # Merge incoming arguments with default arguments
                p = {**GLOBAL_ARGS, **json}
                return self.BuildResponse(RunAction(p, False))

            def put(self):
                return self.BuildResponse(ActionError("Error, PUT not supported"))

            def delete(self):
                return self.BuildResponse(ActionError("Error, DELETE not supported"))

            def PrepateRequest(self):
                log.Dbg("aaa")
                port = request.environ.get('REMOTE_PORT')
                json = self.GetJsonRequest(request)
                log.Dbg("json = " + str(json))
                log.Dbg("Incoming request :: "                              + \
                        "type=" + ("JSON" if request.is_json else "DATA")   + \
                        ", port=" + str(port)                               + \
                        ", status=" + "ok" if json else "not-ok")
                log.Dbg("bbb")
                return json

            def GetJsonRequest(self, request):
                if request.is_json:
                    json = request.get_json()
                else:
                    d = request.get_data(as_text=True)
                    if d and len(d) >= 4 and d[0] == d[1] == '{' and d[-1] == d[-2] == '}':
                        json_str = d[1:-1]
                    else:
                        json_str = None

                    json = Utils.StrToJson(json_str) if json_str else None
                return json

            def BuildResponse(self, action):
                status = 200 if action.Ok() else 400
                resp = make_response(jsonify(action.status), status)
                resp.headers.add('Access-Control-Allow-Origin', '*')
                return resp

        #-------------------------------------------------------------------------------------------
        class GrafanaDs(RestApi):
            def get(self):
                return self.BuildResponse(ActionOk("ok"))

        #-------------------------------------------------------------------------------------------
        class GrafanaDsQuery(RestApi):
            def post(self):
                json = self.PrepateRequest()
                return self.BuildResponse(ActionError("Error, POST not supported"))

            def put(self):
                return self.BuildResponse(ActionError("Error, PUT not supported"))

            def delete(self):
                return self.BuildResponse(ActionError("Error, DELETE not supported"))

        app = Flask(APP_NAME)
        api = Api(app)
        api.add_resource(RestApi, "/api")
        api.add_resource(GrafanaDs, "/")
        api.add_resource(GrafanaDsQuery, "/ds/query")
        app.run(debug=False, host=self.p_addr, port=self.p_port)

#---------------------------------------------------------------------------------------------------
class ActionHttpClient(ActionCmd):
    def __init__(self, proto, addr, port, auth_token, data):
        self.p_proto = proto
        self.p_addr = addr
        self.p_port = port
        self.p_auth_token = auth_token
        self.p_data = data
        super(ActionHttpClient, self).__init__("http-client", 
            OrderedDict({"proto":proto, "addr":addr, "port":port, "auth_token":auth_token, "data":data}))

    def Run(self):
        # Upload data to server
        url_str = self.p_proto + "://" + self.p_addr + ":" + str(self.p_port)
        data_str = Utils.JsonToStr(self.p_data)
        cmd_str = "curl -X POST -s " + url_str + "/api"                 + \
                              " -H \"Content-Type: application/json\""  + \
                              " -d '" +  data_str + "'"
        cmd = ShellCmd(cmd_str)
        if not cmd.Ok():
            return self.SetErr("Error, failed to upload data to server")

        # Check if server responded with valid json
        resp = cmd.OutJson()
        if not resp or "success" not in resp or "out" not in resp: 
            return self.SetErr("Error, server sent invalid response")

        # Check if server succeed
        if not resp["success"]: 
            return self.SetErr("Error, server sent failure in response")

        # Inherit "out" from response
        self.SetOut(resp["out"])

#---------------------------------------------------------------------------------------------------
def RunAction(p, dump_status=True):
    # Read loop param
    loop_num = p.get("loop") if p else 1
    loop_delay = p.get("loop-delay") if p else 0
    loop_sleep_sec = loop_delay / 1000
    is_multi_loop = (loop_num > 1)

    # Loop is allowed only once - all following RunAction() invocations 
    # should not have loop
    p["loop"] = 1

    # Begin loop
    if dump_status and is_multi_loop:
        out.Write("[", new_line=False)

    # Iterate loop
    is_first = True
    action = None
    while loop_num != 0:
        is_last = (loop_num == 1)
        action = RunActionOnce(copy.deepcopy(p))

        # Dump status
        if dump_status:
            prefix = "  " if is_multi_loop and is_first else ""
            suffix = ", " if not is_last else ""
            out.Write(prefix + Utils.JsonToStr(action.status) + suffix, do_flush=False)

        # Next iteration
        is_first = False
        if loop_num != -1:
            loop_num -= 1

        # Bzzz-z-z-z-z-z-z-z-z-z
        if loop_num != 0 and loop_sleep_sec > 0:
            time.sleep(loop_sleep_sec)

    # End loop
    if dump_status and is_multi_loop:
        out.Write("]")
    return action

#---------------------------------------------------------------------------------------------------
def RunActionOnce(p):
    while True:
        action_name = p.get("action") if p else None

        # db-create
        if action_name == "db-create": 
            action = ActionDbCreate(p.get("db-name"))

        # db-write
        elif action_name == "db-write":
            action = ActionDbWrite(p.get("db-name"), p.get("data"), p.get("random"))

        # db-read
        elif action_name == "db-read": 
            action = ActionDbRead(p.get("db-name"), p.get("filter"))

        # sensor-ds18b20
        elif action_name == "sensor-ds18b20":
            action = ActionSensorDs18b20(p.get("sensor-id"), p.get("random"))

        # http-server
        elif action_name == "http-server":
            action = ActionHttpServer(p.get("addr"), p.get("port"))

        # http-client
        elif action_name == "http-client":
            action = ActionHttpClient(p.get("proto"), p.get("addr"), 
                                      p.get("port"), p.get("auth-token"), 
                                      p.get("data"))

        # http-client-sensor-ds18b20
        elif action_name == "http-client-sensor-ds18b20":
            # Read sensor
            p["action"] = "sensor-ds18b20"
            action = RunAction(p, False)
            if not action.Ok():
                break

            # Run HTTP client
            remote_action = OrderedDict({
                "action":"db-write", 
                "db-name":p.get("db-name"), 
                "data": action.OutJson()})
            p = OrderedDict({
                "action":"http-client", 
                "addr":p.get("addr"), 
                "auth-token":p.get("auth-token"), 
                "data": remote_action})
            action = RunAction(p, False)

        # http-client-db-read
        elif action_name == "http-client-db-read":
            # Run HTTP client
            p["action"] = "http-client"
            p["data"] = OrderedDict({
                "action":"db-read", 
                "db-name":p.get("db-name"), 
                "filter": p.get("filter")})
            action = RunAction(p, False)

        # write-sensor-ds18b20
        elif action_name == "write-sensor-ds18b20":
            # Read sensor
            p["action"] = "sensor-ds18b20"
            action = RunAction(p, False)
            if not action.Ok():
                break

            # Write sensor
            p["data"] = action.OutJson()
            p["action"] = "db-write"
            action = RunAction(p, False)

        # error
        else: 
            action = ActionError("Error, unknown action", p)
        break
    return action

#---------------------------------------------------------------------------------------------------
"""
Fucking main
"""
if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description='Piot tool')
    parser.add_argument('--action', action='store', 
        help='Name of the action to perform')
    parser.add_argument('--db-name', action='store', 
        help='Name of the db')
    parser.add_argument('--sensor-id', action='store', 
        help='ID of the sensor')
    parser.add_argument('--data', action='store', type=json.loads, 
        help='Data in JSON format')
    parser.add_argument('--filter', action='store', default=".", 
        help='JQ filter that will be applied on top of JSON output')
    parser.add_argument('--range-from', action='store', default="now-6d", 
        help='Beginning of time range')
    parser.add_argument('--range-to', action='store', default="now", 
        help='End of time range')
    parser.add_argument('--range-interval', action='store', type=int, default=1000, 
        help='Minimal interval duration in range measured in ms')
    parser.add_argument('--range-size', action='store', type=int, default=1024, 
        help='Maximum number of entries in range')
    parser.add_argument('--auth-token', action='store', 
        help='Authentication token when connecting to server')
    parser.add_argument('--proto', action='store', default="http", 
        help='Transport ptotocol (HTTP or HTTPS)')
    parser.add_argument('--addr', action='store', 
        help='Adress of the server')
    parser.add_argument('--port', action='store', type=int, default=8000, 
        help='Listening port of the server')
    parser.add_argument('--random', action='store_true', 
        help='Sensor will report random data instead of reading real values')
    parser.add_argument('--loop', action='store', type=int, default=1, 
        help='Number of loop iterations')
    parser.add_argument('--loop-delay', action='store', type=int, default=0, 
        help='Number of msec to sleep between loop iterations')
    args = parser.parse_args()

    # Log writer
    log = Logger("stdout" if args.action == "http-server" else LOG_FILE)
    log.Dbg(">" * 80)
    log.Dbg("Starting " + APP_NAME + " @ " + str(Utils.GetTimestamp()))

#    ts = Utils.GetUnixTimestamp()
#    for timedef in ("now-5m", "now", "now/d", "now+7w", "now/w", "now-6M", "now-1M/M", "fuck-1x", "now+5y"):
#        ts_new = Utils.GetTimestampFromTimedef(timedef, ts)
#        log.Dbg("def=" + timedef + \
#                " now=" + str(ts) + \
#                " new=" + str(ts_new) + \
#                " diff=" + str((ts_new if ts_new else 0) - ts) + \
#                " dt=" + Utils.GetStringFromTimestamp(ts_new))

    # Stdout writer
    out = Writer(sys.stdout)

    # Build list arguments
    GLOBAL_ARGS = {}
    for key, value in vars(args).items():
        GLOBAL_ARGS[key.replace("_", "-")] = value

    # Fake range
    fake_range = FakeRange(GLOBAL_ARGS) if args.random else None

    # Run action
    action = RunAction(GLOBAL_ARGS, True)
    sys.exit(action.Rc() if action else 0)
