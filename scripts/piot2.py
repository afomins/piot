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
                err = "wrong groups"; break

            # Base
            base = groups[0]
            if base != "now":
                err = "bad base"; break

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
                    err = "bad unit"; break

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

            break # while
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

    dir = "backlog"
    def InitDir(suffix):
        Backlog.dir = "backlog-" + suffix

    def __init__(self, name):
        super(Backlog, self).__init__()
        self._name = name
        self._data_path = Backlog.dir + "/" + name + Backlog.DATA_EXTENSION
        self._meta_path = Backlog.dir + "/" + name + Backlog.META_EXTENSION

        # Validate data & meta
        data_exists = Utils.IsFilePresent(self._data_path)
        meta_exists = Utils.IsFilePresent(self._meta_path)
        if data_exists and meta_exists:
            # TODO: Validate meta
            pass

        elif meta_exists and not data_exists:
            # TODO: clear meta
            pass
        
        elif not meta_exists and data_exists:
            # TODO: Rebuild meta
            pass

        # Test metadata
        self._meta = None
        if Utils.IsFilePresent(self._meta_path):
            self._meta = self.ReadMeta()

    def Write(self, data):
        path = self._data_path
        err = None
        while True:
            if isinstance(data, str):
                data = Utils.StrToJson(data)

            # Data must be list of dicts
            if not data or not isinstance(data, list):
                err = "data is not a list"; break

            # Get backlog config
            time_first = time_last = backlog_size = 0
            if self._meta:
                time_first = self._meta["time-first"]
                time_last = self._meta["time-last"]
                backlog_size = self._meta["size"]

            # Parse all data entries
            data_str = None
            for entry in data:
                if not isinstance(entry, dict):
                    err = "data entry is not a dict"; break

                if not entry["time"]:
                    err = "data entry has no time"; break
                time = entry["time"]

                if not isinstance(time, int):
                    err = "time is not an integer"; break

                if time <= time_last:
                    err = "time does not increase :: time=" + str(time) + \
                                                   " time_last=" + str(time_last); break
                time_last = time

                if time_first == 0:
                    time_first = time

                # Convert entry to string
                if not data_str:
                    data_str = "  " if not Utils.IsFilePresent(path) \
                                        or Utils.IsFileEmpty(path) else ", "
                else:
                    data_str += ", "
                data_str += Utils.JsonToStr(entry) + "\n"
            if err: break

            # Create backlog dir
            if not Utils.IsDirPresent(Backlog.dir) and \
               not Utils.CreateDir(Backlog.dir):
                err = "no dir"; break

            # Write data
            if not Utils.WriteFile(path, data_str, False):
                err = "write error"; break

            # Update meta
            self._meta = self.UpdateMeta(time_first, time_last,
              backlog_size + len(data))

            break # while
        if err:
            self.LogErr("Failed to write backlog :: " + err + " :: path=" + path)
        return not err

    def Read(self):
        data_json = None
        path = self._data_path
        err = None
        while True:
            # Read data as sting
            data = Utils.ReadFile(path)
            if not data:
                data = ""

            # Convert data to json
            data_json = Utils.StrToJson("[" + data + "]")
            if not data_json:
                err = "json parsing failed"; break

            break # while
        if err:
            self.LogErr("Failed to read backlog :: " + err + " :: path=" + path)
        return data_json

    def Clear(self):
        path = self._data_path
        err = None
        while True:
            # Overwrite backlog
            if not Utils.WriteFile(path, "", True):
                err = "write failed"; break
    
            # Update meta
            self._meta = self.UpdateMeta(0, 0, 0)

            break # while
        if err:
            self.LogErr("Faild to clear backlog :: err=" + err + " path=" + path)
        return not err

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
                err = "no body"; break

            # Parse meta file
            data = Utils.StrToJson(body)
            if not data:
                err = "not a json"; break

            # Read meta entries
            time_first = time_last = size = 0
            try:
                time_first = data["time-first"]
                time_last = data["time-last"]
                size = data["size"]
            except:
                err = "no entries"; break

            if not isinstance(time_first, int) or \
               not isinstance(time_last, int) or \
               not isinstance(size, int):
                err = "not an integer entries"; break

            # Validate meta entries
            if time_last < time_first or size < 0:
                err = "bad entries"; break

            break # while
        if err:
            self.LogDbg("Failed to read meta file :: " + err + " :: path=" + path)
            data = None
        return data

    def UpdateMeta(self, time_first, time_last, size):
        self.WriteMeta(time_first, time_last, size)
        return self.ReadMeta()

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
        if out:
            # OrderedDict is list of key-value tuples
            self._is_json = isinstance(out, dict) or isinstance(out, list)
            self._out = out
        return out

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
        err = None
        while True:
            # Write to backlog
            LogTab.PushLogTab(self)
            backlog = Backlog(self._sensor_name)
            if not backlog.Write(self._data):
                err = "write error"; break

            # Set status
            if not self.SetOut(backlog.GetStatus()):
                err = "no status"; break

            break # while
        if err:
            self.SetErr("Failed to write backlog :: " + err);

#---------------------------------------------------------------------------------------------------
class ActionBacklogClear(Action):
    def __init__(self, sensor_name):
        self._sensor_name = sensor_name
        super(ActionBacklogClear, self).__init__("backlog-clear",
          OrderedDict({"sensor-name":sensor_name}))

    def Run(self):
        err = None
        while True:
            # Clear to backlog
            LogTab.PushLogTab(self)
            backlog = Backlog(self._sensor_name)
            if not backlog.Clear():
                err = "clear error"; break

            # Set status
            if not self.SetOut(backlog.GetStatus()):
                err = "no status"; break

            break # while
        if err:
            self.SetErr("Failed to clear backlog :: " + err)

#---------------------------------------------------------------------------------------------------
class ActionBacklogRead(Action):
    def __init__(self, sensor_name):
        self._sensor_name = sensor_name
        super(ActionBacklogRead, self).__init__("backlog-read",
          OrderedDict({"sensor-name":sensor_name}))

    def Run(self):
        err = None
        while True:
            # Read backlog
            LogTab.PushLogTab(self)
            backlog = Backlog(self._sensor_name)
            data = backlog.Read()

            # Set status
            status = backlog.GetStatus()
            if not status:
                err = "no status"; break

            # Write data to status
            status["data"] = data
            self.SetOut(status)

            break # while
        if err:
            self.SetErr("Failed to read backlog :: " + err)

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
            err = None
            while True:
                # Load kernel modules
                LogTab.PushLogTab(self)
                if not ShellCmd("sudo modprobe w1-gpio && sudo modprobe w1-therm").Ok():
                    err = "load modules error"; break

                # Read sensor data
                value_raw = Utils.ReadFile( \
                  self.DS18B20_PATH + "/" + str(self._id) + "/" + self.DS18B20_DATA)
                if not value_raw:
                    err = "no value"; break
                value = value_raw / 1000

                break # while
            if err:
                self.SetErr("Failed to read sensor Ds18b20 :: " + err)

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
                return self.BuildResponse(
                  RunAction(self.PrepateRequest("post"), 
                            ActionHttpServer.ALLOWED_ACTIONS))

            def put(self):
                return self.BuildErrorResponse("put")

            def delete(self):
                return self.BuildErrorResponse("delete")

            def GetJsonRequest(self, request):
                if request.is_json:
                    json = request.get_json(silent=True)
                else:
                    d = request.get_data(as_text=True)
                    if d and len(d) >= 4 and d[0] == d[1] == '{' and d[-1] == d[-2] == '}':
                        json_str = d[1:-1]
                    else:
                        json_str = None
                    json = Utils.StrToJson(json_str) if json_str else None
                return json

            def PrepateRequest(self, method):
                port = request.environ.get('REMOTE_PORT')
                json = self.GetJsonRequest(request)
                log.Dbg("." * 80)
                log.Dbg("Incoming request :: "                                + \
                        "time=" + str(Utils.GetTimestamp())                   + \
                        ", method=" + method                                  + \
                        ", port=" + str(port)                                 + \
                        ", json=" + ("yes" if json else "no"))
                return json if json else {}

            def BuildResponse(self, action):
                return make_response(jsonify(action._status), 200)

            def BuildErrorResponse(self, method):
                return self.BuildResponse(
                  ActionError(method + " not supported", 
                              self.PrepateRequest(method)))

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

        err = None
        while True:
            # Send HTTP request
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
                # Bad HTTP status
                pass
            except:
                err = "send error"; break

            # Test response
            if not resp or not resp_data:
                err = "no response"; break

            # Parse response
            if not self.SetOut(Utils.StrToJson(resp_data)):
                err = "bad response"; break

            # Test status
            if resp.status != 200:
                err = "bad response :: reason=" + str(resp.reason) + \
                                     " status=" + str(resp.status); break

            break # while
        if err:
            self.SetErr("Failed to run http client :: " + err)

#---------------------------------------------------------------------------------------------------
def RunAction(args, allowed=None):
    action = None
    err = None
    while True:
        # Sanity check arguments
        if not args or not isinstance(args, dict):
            args = {}
            err = "bad arguments"; break

        # Get name of the action
        name = args.get("action")
        if not name:
            err = "no action"; break

        # Filter actions
        if allowed and name not in allowed:
            err = "not allowed"; break

        #-------------------------------------------------------------------------------------------
        # DB
        #-------------------------------------------------------------------------------------------
        # db-init
        if name == "db-init":
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

        # backlog-clean
        elif name == "backlog-clear":
            action = ActionBacklogClear(
                args.get("sensor-name"));
            pass

        #-------------------------------------------------------------------------------------------
        # SENSORS
        #-------------------------------------------------------------------------------------------
        # read-sensor-ds18b20
        elif name == "read-sensor-ds18b20":
            action = ActionReadSensorDs18b20(
                args.get("sensor-id"),
                args.get("random"))

        # error
        if not action:
            err = "unknown action"; break

        break # while
    if err:
        action = ActionError("Failed to run action :: " + err, args);

    # Log to terminal
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
