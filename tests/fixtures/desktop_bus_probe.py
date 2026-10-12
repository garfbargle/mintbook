import importlib.machinery,importlib.util,json,os,signal,sys,time
from pathlib import Path
os.environ['GIO_USE_VFS']='local'
os.environ['DBUS_SYSTEM_BUS_ADDRESS']=os.environ['DBUS_SESSION_BUS_ADDRESS']
import gi
gi.require_version('Gio','2.0')
from gi.repository import Gio,GLib
loader=importlib.machinery.SourceFileLoader('status',sys.argv[1]);m=importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name,loader));loader.exec_module(m)
m.read_backend=lambda name,render_only=False:('<txt>'+name+'</txt>',None)
c=m.Collector(GLib,Gio);c.cpu.WATCHER='/nonexistent';c.session.session_pid=lambda:int(sys.argv[2]);bus=Gio.bus_get_sync(Gio.BusType.SESSION,None);results={}
for name in ('org.freedesktop.NetworkManager','org.freedesktop.login1'):
 bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','RequestName',GLib.Variant('(su)',(name,0)),GLib.VariantType.new('(u)'),Gio.DBusCallFlags.NONE,2000,None)
def noisy():
 results['before_noise']=c.reads['wifi']
 for n in range(20):bus.emit_signal(None,'/org/freedesktop/NetworkManager/Devices/1','org.freedesktop.DBus.Properties','PropertiesChanged',GLib.Variant('(sa{sv}as)',('Device.Statistics',{'RxBytes':GLib.Variant('t',n)},[])))
 return False
def useful():
 results['after_noise']=c.reads['wifi']
 bus.emit_signal(None,'/org/freedesktop/NetworkManager/Devices/1','org.freedesktop.DBus.Properties','PropertiesChanged',GLib.Variant('(sa{sv}as)',('Device.Wireless',{'Strength':GLib.Variant('y',80)},[])))
 return False
def resume():
 results['after_strength']=c.reads['wifi']
 Path(c.cpu.STATE).write_text('old');Path(c.cpu.PROCS).write_text('old');(m.CACHE.parent/'cpu.io').write_text('old')
 bus.emit_signal(None,'/org/freedesktop/login1','org.freedesktop.login1.Manager','PrepareForSleep',GLib.Variant('(b)',(False,)))
 return False
def session_exit():
 results['resume_baseline_reset']=Path(c.cpu.STATE).read_text()!='old' and Path(c.cpu.PROCS).read_text()!='old'
 os.kill(int(sys.argv[2]),signal.SIGTERM);return False
GLib.timeout_add(500,noisy);GLib.timeout_add(1000,useful);GLib.timeout_add(1500,resume);GLib.timeout_add(2200,session_exit)
start=time.monotonic();results['exit']=c.run();results['milliseconds']=round((time.monotonic()-start)*1000);results['heartbeat_removed']=not(m.CACHE/'heartbeat').exists();print(json.dumps(results))
