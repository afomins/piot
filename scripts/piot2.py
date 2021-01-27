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
import re
from collections import OrderedDict

#---------------------------------------------------------------------------------------------------
APP_NAME = "piot2"
LOG_FILE = "/tmp/" + APP_NAME + ".log"
SECONDS = { "s" : 1, 
            "m" : 60, 
            "h" : 60 * 60,
            "d" : 60 * 60 * 24,
            "w" : 60 * 60 * 24 * 7,
            "M" : None,
            "y" : None}

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

    def GetTimestampFromString(val, fmt="%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            dt = datetime.datetime.strptime(val, fmt)
            ts = datetime.datetime.timestamp(dt)
            return ts
        except:
            return None

    def GetStringFromTimestamp(val, fmt="%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.datetime.fromtimestamp(val).strftime(fmt)
        except:
            return "error"

    def GetTimestampFromTimedef(timedef, now_ts=None):
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

    def CreateDir(name):
        try:
            os.mkdir(name)
        except:
            return False
        return True

    def SplitLines(lines, prefix, cb):
        first = True
        for l in lines.splitlines():
            cb(prefix + l)
            if first:
                prefix = " " * len(prefix)
                first = False

    def LogLines(log_level, prefix, line, tab_num = 0):
        def cb(line):
            log.Log(log_level, line, tab_num)
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

    def ReadFileLines(path):
        body = []
        try:
            f = open(path, "r")
            if f and f.mode == "r":
                body = f.readlines()
        except:
            pass
        return body

    def WriteFile(path, body, clear_file):
        try:
            with open(path, "w" if clear_file else "a") as f:
                f.write(body)
        except:
            return False
        return True

    def JsonToStr(json_obj, indent = None):
        try:
            return str(json.dumps(json_obj, indent = indent))
        except:
            return "{}"

    def StrToJson(str, indent = None):
        try:
            return json.loads(str)
        except:
            return None

    def GetHostname():
        return socket.gethostname()

    def GetUptime():
        try:
            with open('/proc/uptime', 'r') as f:
                sec = float(f.readline().split()[0])
                return int(sec)
        except:
            return 0

#---------------------------------------------------------------------------------------------------
class Writer:
    def __init__(self, stream):
        self._stream = stream

    def Write(self, str, flush=True, new_line=True):
        if not self._stream:
            return
        if new_line:
            str += "\n"
        self._stream.write(str)
        if flush:
            self._stream.flush()

#---------------------------------------------------------------------------------------------------
class Logger(Writer):
    def __init__(self, dest, clean_log=False):
        stream = None
        if dest == "stdout":
            stream = sys.stdout
        else:
            try:
                stream = open(LOG_FILE, "w" if clean_log else "a")
            except:
                pass
        super(Logger, self).__init__(stream)

    def Log(self, prefix, line, tab_num):
        tab_filler = " " + '...' * tab_num + " "
        self.Write(prefix + tab_filler + line, flush=False)

    def Dbg(self, line, tab_num = 0):
        self.Log("DBG", line, tab_num)

    def Inf(self, line, tab_num = 0):
        self.Log("INF", line, tab_num)

    def Err(self, line, tab_num = 0):
        self.Log("ERR", line, tab_num)

#---------------------------------------------------------------------------------------------------
class LogTab:
    _tab = 0

    def PushLogTab(lt):
        LogTab._tab = lt._log_tab + 1

    def PopLogTab():
        value = LogTab._tab
        LogTab._tab -= 1
        return value

    def __init__(self):
        self._log_tab = LogTab.PopLogTab()

    def Log(self, prefix, line):
        log.Log(prefix, line, self._log_tab)

    def LogDbg(self, line):
        log.Dbg(line, self._log_tab)

    def LogInf(self, line):
        log.Inf(line, self._log_tab)

    def LogErr(self, line):
        log.Err(line, self._log_tab)

#---------------------------------------------------------------------------------------------------
class Backlog(LogTab):
    DATA_EXTENSION = ".piot2"
    META_EXTENSION = ".piot2.meta"

    _dir = "backlog"
    def InitDir(suffix):
        Backlog._dir = "backlog-" + suffix

    def __init__(self, name):
        super(Backlog, self).__init__()
        self._name = name
        self._data_path = Backlog._dir + "/" + name + Backlog.DATA_EXTENSION
        self._meta_path = Backlog._dir + "/" + name + Backlog.META_EXTENSION

        # Metadata
        self._meta = None
        if Utils.IsFilePresent(self._meta_path):
            self._meta = self.ReadMeta()
            if not self._meta:
                # TODO: Rebuild meta file
                pass

    def Write(self, data):
        err = None
        path = self._data_path
        while True:
            if isinstance(data, str):
                data = Utils.StrToJson(data)

            if not data or not isinstance(data, dict):
                err = "data is not a json"
                break

            if not data["time"]:
                err = "no time"
                break
            time = data["time"]

            if not isinstance(time, int):
                err = "time is not an integer"
                break

            # Time must increase
            if self._meta and time <= self._meta["time-last"]:
                err = "bad time"
                break

            # Create backlog dir
            if not Utils.IsDirPresent(Backlog._dir) and not Utils.CreateDir(Backlog._dir):
                err = "dir create error"
                break

            # Write data
            prefix = "  " if not Utils.IsFilePresent(path) or Utils.IsFileEmpty(path) else ", "
            rc = Utils.WriteFile(path, prefix + Utils.JsonToStr(data) + "\n", False)
            if not rc:
                err = "file write error"
                break

            # Write meta
            self.WriteMeta(
              self._meta["time-first"] if self._meta else time,
              time,
              self._meta["size"] + 1 if self._meta else 1)

            # Update meta
            self._meta = self.ReadMeta()
            break

        if err:
            log.Err("Failed to write backlog :: " + err + " :: path=" + path)
        return not err

    def Read(self):
        err = None
        data_json = None
        path = self._data_path
        while True:
            # Read data as sting
            data = Utils.ReadFile(path)
            if not data:
                data = ""

            # Convert data to json
            data_json = Utils.StrToJson("[" + data + "]")
            if not data_json:
                err = "json parsing failed"
                break
            break

        if err:
            log.Err("Failed to read backlog :: " + err + " :: path=" + path)
        return data_json

    def WriteMeta(self, time_first, time_last, size):
        data = OrderedDict({            \
            "time-first" : time_first,  \
            "time-last"  : time_last,
            "size"       : size})
        Utils.WriteFile(self._meta_path, Utils.JsonToStr(data), True)

    def ReadMeta(self):
        data = None
        err = None
        path = self._meta_path
        while True:
            # Read meta file
            body = Utils.ReadFile(path)
            if not body:
                err = "no body";
                break

            # Parse meta file
            data = Utils.StrToJson(body)
            if not data:
                err = "not a json";
                break

            # Read meta entries
            time_first = time_last = size = 0
            try:
                time_first = data["time-first"]
                time_last = data["time-last"]
                size = data["size"]
            except:
                err = "no entries";
                break

            if not isinstance(time_first, int) or not isinstance(time_last, int) or \
               not isinstance(size, int):
                err = "not an integer entries"
                break

            # Validate meta entries
            if time_last < time_first or size < 0:
                err = "bad entries";
                break

            break

        if err:
            self.LogDbg("Failed to read meta file :: " + err + " :: path=" + path)
            data = None
        return data

    def GetStatus(self):
        status = None
        if self._meta:
            return OrderedDict({"age"  : self._meta["time-last"] - self._meta["time-first"], \
                                "size" : self._meta["size"]})
        return status

#---------------------------------------------------------------------------------------------------
class CmdResult(LogTab):
    def __init__(self):
        super(CmdResult, self).__init__()
        self._is_json = False
        self._out = ""
        self._err = ""
        self._rc = 0

    def SetOut(self, out):
        # OrderedDict is list of key-value tuples
        self._is_json = isinstance(out, dict) or isinstance(out, list)
        self._out = out

    def SetErr(self, err = "hmm... something went wrong :(", rc = 42):
        self._err = err
        self._rc = rc

    def Ok(self):
        return self._rc == 0

    def Rc(self):
        return self._rc

    def IsJson(self):
        return self._is_json

    def OutStr(self):
        return self._out if not self._is_json \
                         else Utils.JsonToStr(self._out)

    def OutJson(self):
        return self._out if self._is_json \
                         else Utils.StrToJson(self._out)

    def Err(self):
        return self._err

#---------------------------------------------------------------------------------------------------
class Cmd(CmdResult):
    def __init__(self, cmd):
        super(Cmd, self).__init__()
        self._cmd = cmd

        # Prepare command 
        self.Prepare()

        # Run command
        if self.Ok():
            self.Run()

        # Finalize command
        self.Finalize()

        # Write log
        self.LogDbg(">> rc  = " + str(self.Rc()))
        out_str = self.OutStr()
        if out_str and len(out_str) > 0:
            Utils.LogLines("DBG", ">> out = ", out_str, self._log_tab)
        err_str = self.Err()
        if err_str and len(err_str) > 0:
            Utils.LogLines("DBG", ">> err = ", err_str, self._log_tab)

    def Prepare(self):
        pass

    def Run(self):
        return True

    def Finalize(self):
        pass

#---------------------------------------------------------------------------------------------------
class ShellCmd(Cmd):
    def __init__(self, cmd):
        super(ShellCmd, self).__init__(cmd)

    def Prepare(self):
        self.LogDbg("Running shell command :: cmd=" + self._cmd)

    def Run(self):
        ret = subprocess.run(self._cmd, shell = True, stdout=subprocess.PIPE, stderr = subprocess.PIPE)
        self.SetOut(ret.stdout.decode("utf-8").strip())
        self.SetErr(ret.stderr.decode("utf-8").strip(), ret.returncode)

#---------------------------------------------------------------------------------------------------
class Action(Cmd):
    def __init__(self, cmd, args):
        self._args = args
        self._status = OrderedDict()
        self._status["action"] = cmd
        self._status["args"] = OrderedDict({})
        super(Action, self).__init__(cmd)

    def Prepare(self):
        # Test mandatory arguments
        is_ok = True
        dest_args = self._status["args"]
        for k, v in self._args.items():
            dest_args[k] = str(v)
            if v == None:
                is_ok = False

        # Fail if mandatory parameters are missing
        if not is_ok:
            self.SetErr("Error, mandatory arguments are missing")

        # Log
        self.LogDbg("")
        self.LogDbg("Running action :: " + Utils.JsonToStr(self._status))

    def Finalize(self):
        # Set success
        self._status["success"] = self.Ok()

        # Set error message
        err_str = self.Err()
        if len(err_str) > 0:
            self._status["error"] = err_str

        # Set output
        self._status["out"] = self.OutJson()

#---------------------------------------------------------------------------------------------------
class ActionError(Action):
    def __init__(self, msg, args):
        self._msg = msg
        super(ActionError, self).__init__("error", args)

    def Run(self):
        self.SetErr(self._msg)

#---------------------------------------------------------------------------------------------------
class ActionDbCreate(Action):
    def __init__(self, auth_token):
        super(ActionDbCreate, self).__init__("db-create", log_tab, 
          OrderedDict({"auth-token":auth_token}))

    def Run(self):
        pass

#---------------------------------------------------------------------------------------------------
class ActionBacklogWrite(Action):
    def __init__(self, sensor_name, data):
        self._sensor_name = sensor_name
        self._data = data
        super(ActionBacklogWrite, self).__init__("backlog-write",
          OrderedDict({"sensor-name":sensor_name, "data":data}))

    def Run(self):
        while True:
            # Write to backlog
            LogTab.PushLogTab(self)
            backlog = Backlog(self._sensor_name)
            if not backlog.Write(self._data):
                self.SetErr("Failed to write to backlog")
                break

            # Report status
            status = backlog.GetStatus()
            if status:
                self.SetOut(status)
            else:
                self.SetErr("Failed to get backlog status")
            break

#---------------------------------------------------------------------------------------------------
class ActionBacklogRead(Action):
    def __init__(self, sensor_name):
        self._sensor_name = sensor_name
        super(ActionBacklogRead, self).__init__("backlog-read",
          OrderedDict({"sensor-name":sensor_name}))

    def Run(self):
        while True:
            # Read backlog
            LogTab.PushLogTab(self)
            backlog = Backlog(self._sensor_name)
            data = backlog.Read()

            # Report status
            status = backlog.GetStatus()
            if status:
                status["data"] = data
                self.SetOut(status)
            else:
                self.SetErr("Failed to get backlog status")
            break

#---------------------------------------------------------------------------------------------------
class ActionReadSensorDs18b20(Action):
    DS18B20_PATH = "/sys/bus/w1/devices"
    DS18B20_DATA = "w1_slave"

    def __init__(self, id, random):
        self._id = id
        self._random = random
        super(ActionReadSensorDs18b20, self).__init__("sensor-ds18b20",
          OrderedDict({"sensor-id":id, "random":random}))

    def Run(self):
        value = None
        if self._random:
            value = random.randrange(-10, 100)

        else:
            while True:
                # Load kernel modules
                LogTab.PushLogTab(self)
                if not ShellCmd("sudo modprobe w1-gpio && sudo modprobe w1-therm").Ok():
                    self.SetErr("Failed to load sensor modules")
                    break

                # Read sensor data
                value_raw = Utils.ReadFile( \
                  self.DS18B20_PATH + "/" + str(self._id) + "/" + self.DS18B20_DATA)
                if not value_raw:
                    self.SetErr("Failed to read sensor value")
                    break

                value = value_raw / 1000
                break

        # Save sensor data
        data = OrderedDict()
        if value != None:
            data["time"] = Utils.GetUnixTimestamp()
            data["value"] = value
            data["uptime"] = Utils.GetUptime()
        self.SetOut(data)

#---------------------------------------------------------------------------------------------------
class ActionHttpServer(Action):
    ALLOWED_ACTIONS = ["backlog-write", "read-sensor-ds18b20"]

    def __init__(self, addr, port):
        self._addr = addr
        self._port = port
        super(ActionHttpServer, self).__init__("http-server", 
          OrderedDict({"addr":addr, "port":port}))

    def Run(self):
        from flask import Flask, jsonify, make_response
        from flask_restful import Api, Resource, request

        #-------------------------------------------------------------------------------------------
        class RestApi(Resource):
            def get(self):
                return self.BuildErrorResponse("get")

            def post(self):
                log.Dbg("JJFK :: 1")
                return self.BuildResponse(
                  RunAction(self.PrepateRequest("post"), 
                            ActionHttpServer.ALLOWED_ACTIONS))

            def put(self):
                return self.BuildErrorResponse("put")

            def delete(self):
                return self.BuildErrorResponse("delete")

            def PrepateRequest(self, method):
                log.Dbg("JJFK :: 2")
                port = request.environ.get('REMOTE_PORT')
                log.Dbg("JJFK :: 3")
                json = self.GetJsonRequest(request)
                log.Dbg("JJFK :: 4")
                log.Dbg("." * 80)
                log.Dbg("JJFK :: 5 :: json=" + str(json))
                log.Dbg("Incoming request :: "                                + \
                        "time=" + str(Utils.GetTimestamp())                   + \
                        ", method=" + method                                  + \
                        ", data=" + ("json" if request.is_json else "string") + \
                        ", port=" + str(port)                                 + \
                        ", status=" + "ok" if json else "not-ok")
                log.Dbg("JJFK :: 6")
                return json

            def GetJsonRequest(self, request):
                if request.is_json:
                    json = request.get_json()
                else:
                    d = request.get_data(as_text = True)
                    if d and len(d) >= 4 and d[0] == d[1] == '{' and d[-1] == d[-2] == '}':
                        json_str = d[1:-1]
                    else:
                        json_str = None

                    json = Utils.StrToJson(json_str) if json_str else None
                return json

            def BuildResponse(self, action):
                status = 200 if action.Ok() else 400
                resp = make_response(jsonify(action._status), status)
#                resp.headers.add('Access-Control-Allow-Origin', '*')
                return resp

            def BuildErrorResponse(self, method):
                return self.BuildResponse(
                  ActionError(method + " not supported", 
                              self.PrepateRequest(type)))

        app = Flask(APP_NAME)
        api = Api(app)
        api.add_resource(RestApi, "/api")
        app.run(debug=False, host=self._addr, port=self._port)

#---------------------------------------------------------------------------------------------------
class ActionHttpClient(Action):
    def __init__(self, proto, addr, port, auth_token, data):
        self._proto = proto
        self._addr = addr
        self._port = port
        self._auth_token = auth_token
        self._data = data
        super(ActionHttpClient, self).__init__("http-client", 
          OrderedDict({"proto":proto, "addr":addr, "port":port, "auth-token":auth_token, "data":data}))

    def Run(self):
        from urllib import request
        from urllib import error
        while True:
            req = request.Request(
              method="POST",
              url=self._proto + "://" + self._addr + ":" + str(self._port) + "/api",
              headers={"Content-type":"application/json"},
              data=self._data.encode("utf-8"))
            resp = None
            try:
                resp = request.urlopen(req)
                resp_data = resp.read()
            except error.HTTPError as e:
                pass
            except:
                self.SetErr("Failed to send URL request")
                break

            if not resp or not resp_data:
                self.SetErr("Failed to read response")
                break

            json = Utils.StrToJson(resp_data)
            if not json:
                self.SetErr("Failed to parse response")
                break
            else:
                self.SetOut(json)

            if resp.status != 200:
                self.SetErr("Bad response :: " + resp.reason, resp.status)
                break
            break

#---------------------------------------------------------------------------------------------------
def RunAction(args, allowed=None):
    while True:
        # Filter actions
        name = args.get("action") if args else None
        if allowed and name not in allowed:
            action = ActionError("Action not allowed", args)

        #-------------------------------------------------------------------------------------------
        # DB
        #-------------------------------------------------------------------------------------------
        # db-init
        elif name == "db-init":
#            action = ActionDbInit(
#                args.get("auth-token"))
            pass

        # db-sensor-init
        elif name == "db-sensor-init":
#            action = ActionDbSensorInit(
#                args.get("auth-token"),
#                args.get("sensor-name"),
#                args.get("sensor-type"))
            pass

        # db-sensor-write
        elif name == "db-sensor-write":
#            action = ActionDbSensorWrite(
#                args.get("auth-token"),
#                args.get("sensor-name"),
#                args.get("data"))
            pass

        # db-sensor-read
        elif name == "db-sensor-read":
#            action = ActionDbSensorRead(
#                args.get("auth-token"), 
#                args.get("sensor-name"), 
#                args.get("range-from"), 
#                args.get("range-to"), 
#                args.get("range-size"))
            pass

        #-------------------------------------------------------------------------------------------
        # HTTP
        #-------------------------------------------------------------------------------------------
        # http-server
        elif name == "http-server":
            action = ActionHttpServer(
                args.get("addr"),
                args.get("port"))
            pass

        # http-client
        elif name == "http-client":
            action = ActionHttpClient(
                args.get("proto"), 
                args.get("addr"),
                args.get("port"), 
                args.get("auth-token"),
                args.get("data"))
            pass

        #-------------------------------------------------------------------------------------------
        # BACKLOG
        #-------------------------------------------------------------------------------------------
        # backlog-read
        elif name == "backlog-read":
            action = ActionBacklogRead(
                args.get("sensor-name"));

        # backlog-write
        elif name == "backlog-write":
            action = ActionBacklogWrite(
                args.get("sensor-name"),
                args.get("data"));

        #-------------------------------------------------------------------------------------------
        # SENSORS
        #-------------------------------------------------------------------------------------------
        # read-sensor-ds18b20
        elif name == "read-sensor-ds18b20":
            action = ActionReadSensorDs18b20(
                args.get("sensor-id"),
                args.get("random"))

        # error
        else: 
            action = ActionError("Unknown action", args)
        break

    # Log to console
    out.Write(Utils.JsonToStr(action._status), flush=True)
    return action

#---------------------------------------------------------------------------------------------------
"""
Fucking main
"""
if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description='Piot2 tool')
    parser.add_argument('--action', action='store', 
        help='Name of the action to perform')
    parser.add_argument('--sensor-id', action='store', 
        help='Unique id of the sensor')
    parser.add_argument('--sensor-name', action='store', 
        help='Name of the sensor in db')
    parser.add_argument('--sensor-type', action='store', 
        help='Type of the sensor')
    parser.add_argument('--data', action='store', 
        help='Data in JSON format')
    parser.add_argument('--range-from', action='store', default="now-6d", 
        help='Beginning of time range')
    parser.add_argument('--range-to', action='store', default="now", 
        help='End of time range')
    parser.add_argument('--range-size', action='store', type=int, default=32, 
        help='Maximum number of entries in range')
    parser.add_argument('--proto', action='store', default="http", 
        help='Transport protocol (HTTP or HTTPS)')
    parser.add_argument('--auth-token', action='store', 
        help='Authentication token')
    parser.add_argument('--addr', action='store', default="localhost",
        help='Address of the server')
    parser.add_argument('--port', action='store', type=int, default=8000, 
        help='Listening port of the server')
    parser.add_argument('--random', action='store_true', 
        help='Force sensor to report random data instead of reading real values')
    parser.add_argument('--clean-log', action='store_true', 
        help='Clean log file')

    # Build list arguments
    args = {}
    for key, value in vars(parser.parse_args()).items():
        args[key.replace("_", "-")] = value

    # Init logger writer
    log = Logger("stdout" if args["action"] == "http-server" \
                          else LOG_FILE, args["clean-log"])
    log.Dbg(">" * 80)
    log.Dbg("Starting " + APP_NAME + " @ " + str(Utils.GetTimestamp()))

    # Init stdout writer
    out = Writer(sys.stdout)

    # Init backlog directory
    Backlog.InitDir("server" if args["action"] == "http-server" else "client")

    # Run action
    action = RunAction(args)
    sys.exit(action.Rc() if action else 0)
