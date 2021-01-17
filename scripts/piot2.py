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

    def AppendFile(path, body):
        with open(path, "a") as f:
            f.write(body)

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
        self._stream = stream

    def Write(self, str, flush = True, new_line = True):
        if not self._stream:
            return
        if new_line:
            str += "\n"
        self._stream.write(str)
        if flush:
            self._stream.flush()

#---------------------------------------------------------------------------------------------------
class Logger(Writer):
    def __init__(self, dest, clean_log = False):
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
        self.Write(prefix + tab_filler + line, flush = False)

    def Dbg(self, line, tab_num = 0):
        self.Log("DBG", line, tab_num)

    def Inf(self, line, tab_num = 0):
        self.Log("INF", line, tab_num)

    def Err(self, line, tab_num = 0):
        self.Log("ERR", line, tab_num)

#---------------------------------------------------------------------------------------------------
class CmdResult:
    def __init__(self):
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
    def __init__(self, cmd, log_tab_num):
        super(Cmd, self).__init__()
        self._cmd = cmd
        self._log_tab_num = log_tab_num

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
        if len(out_str) > 0:
            Utils.LogLines("DBG", ">> out = ", out_str, self._log_tab_num)
        err_str = self.Err()
        if len(err_str) > 0:
            Utils.LogLines("DBG", ">> err = ", err_str, self._log_tab_num)

    def Prepare(self):
        pass

    def Run(self):
        return True

    def Finalize(self):
        pass
    
    def Log(self, prefix, line):
        log.Log(prefix, line, self._log_tab_num)

    def LogDbg(self, line):
        log.Dbg(line, self._log_tab_num)

    def LogInf(self, line):
        log.Inf(line, self._log_tab_num)

    def LogErr(self, line):
        log.Err(line, self._log_tab_num)

#---------------------------------------------------------------------------------------------------
class ShellCmd(Cmd):
    def __init__(self, cmd, log_tab_num):
        super(ShellCmd, self).__init__(cmd, log_tab_num)

    def Prepare(self):
        self.LogDbg("Running shell command :: cmd=" + self._cmd)

    def Run(self):
        ret = subprocess.run(self._cmd, shell = True, stdout=subprocess.PIPE, stderr = subprocess.PIPE)
        self.SetOut(ret.stdout.decode("utf-8").strip())
        self.SetErr(ret.stderr.decode("utf-8").strip(), ret.returncode)

#---------------------------------------------------------------------------------------------------
class Action(Cmd):
    def __init__(self, cmd, log_tab_num, args):
        self._args = args
        self._status = OrderedDict()
        self._status["action"] = cmd
        self._status["args"] = OrderedDict({})
        super(Action, self).__init__(cmd, log_tab_num)

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
            self._status["message"] = err_str

        # Set output
        self._status["out"] = self.OutJson()

#---------------------------------------------------------------------------------------------------
class ActionError(Action):
    def __init__(self, msg, args):
        self._msg = msg
        self._orig_args = args
        super(ActionError, self).__init__("error", 1, {})

    def Run(self):
        self.SetErr(self._msg)
        self.SetOut(self._orig_args)

#---------------------------------------------------------------------------------------------------
class ActionDbCreate(Action):
    def __init__(self, log_tab_num, auth_token):
        super(ActionDbCreate, self).__init__("db-create", log_tab_num, 
          OrderedDict({"auth-token":auth_token}))

    def Run(self):
        pass

#---------------------------------------------------------------------------------------------------
class ActionBacklogWrite(Action):
    def __init__(self, sensor_name, data):
        self._sensor_name = sensor_name
        self._data = data
        super(ActionBacklogWrite, self).__init__("backlog-write", 1,
          OrderedDict({"sensor-name":sensor_name, "data":data}))

    def Run(self):
        while True:
            # Initialize backlog file
            tab = self._log_tab_num + 1
            path = "backlog/" + self._sensor_name
            if not ShellCmd("mkdir -p backlog && touch " + path, tab).Ok():
                self.SetErr("Error, failed init backlog")
                break

            # Write data to backlog
            prefix = "  " if Utils.IsFileEmpty(path) else ", "
            Utils.AppendFile(path, prefix + self._data + "\n")
            break

        # Save sensor data
        data = OrderedDict()
        data["path"] = os.environ['HOME'] + "/" + path
        self.SetOut(data)

#---------------------------------------------------------------------------------------------------
class ActionReadSensorDs18b20(Action):
    DS18B20_PATH = "/sys/bus/w1/devices"
    DS18B20_DATA = "w1_slave"

    def __init__(self, id, random):
        self._id = id
        self._random = random
        super(ActionReadSensorDs18b20, self).__init__("sensor-ds18b20", 1,
          OrderedDict({"sensor-id":id, "random":random}))

    def Run(self):
        value = None
        if self._random:
            value = random.randrange(-10, 100)

        else:
            while True:
                # Load kernel modules
                if not ShellCmd("sudo modprobe w1-gpio && sudo modprobe w1-therm", self._log_tab_num + 1).Ok():
                    self.SetErr("Error, failed to load sensor modules")
                    break

                # Read sensor data
                value_raw = Utils.ReadFile( \
                  self.DS18B20_PATH + "/" + str(self._id) + "/" + self.DS18B20_DATA)
                if not value_raw:
                    self.SetErr("Error, failed to read sensor value")
                    break

                value = value_raw / 1000
                break

        # Save sensor data
        data = OrderedDict()
        if value != None:
            data["time"] = Utils.GetUnixTimestamp()
            data["value"] = value
        self.SetOut(data)

#---------------------------------------------------------------------------------------------------
def RunAction(args):
    while True:
        name = args.get("action") if args else None

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
#            action = ActionHttpServer(
#                args.get("addr"),
#                args.get("port"))
            pass

        # http-client
        elif name == "http-client":
#            action = ActionHttpClient(
#                args.get("proto"), 
#                args.get("addr"),
#                args.get("port"), 
#                args.get("auth-token"),
#                args.get("data"))
            pass

        #-------------------------------------------------------------------------------------------
        # BACKLOG
        #-------------------------------------------------------------------------------------------
        # backlog-read
        elif name == "backlog-read":
#            action = ActionBacklogRead(
#                args.get("sensor-name"));
            pass

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
            action = ActionError("Error, unknown action", args)
        break

    # Log 
    out.Write(Utils.JsonToStr(action._status), flush = False)
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
    parser.add_argument('--addr', action='store', 
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

    # Log writer
    log = Logger("stdout" if args["action"] == "http-server" else LOG_FILE, args["clean-log"])
    log.Dbg(">" * 80)
    log.Dbg("Starting " + APP_NAME + " @ " + str(Utils.GetTimestamp()))

    # Stdout writer
    out = Writer(sys.stdout)

    # Run action
    action = RunAction(args)
    sys.exit(action.Rc() if action else 0)
