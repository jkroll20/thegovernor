#!/usr/bin/python
# thegovernor - Switch CPU governor from notification area
# Copyright (C) 2015 Johannes Kroll
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import os, sys
import subprocess
import glob
import gtk
import glib
import json
import time

def sendnotification(message):
    subprocess.Popen(['notify-send', message])

class Config:
    def __init__(self, appname, defaults):
        self.filename= os.path.join(glib.get_user_config_dir(), appname + ".json")
        self.settings= defaults
        try:
            filesettings= json.load(open(self.filename))
            for setting in filesettings:
                self.settings[setting]= filesettings[setting]
        except Exception as ex:
            print("while loading %s: %s" % (self.filename, str(ex)))
    
    def get(self, name):
        if name in self.settings:
            return self.settings[name]
        return None
    
    def set(self, name, value):
        self.settings[name]= value
        self.sync()
    
    def sync(self):
        json.dump(self.settings, open(self.filename, "w"))
    

def add_watch(path, callback):
    # create an inotify CLOSE_WRITE watch for path for use with gtk+ main loop
    try:
        import inotifyx
        fd= inotifyx.init()
        wd= inotifyx.add_watch(fd, path, inotifyx.IN_CLOSE_WRITE)
        def handle_watch(source, condition):
            inotifyx.get_events(fd)
            callback(path)
            sys.stdout.flush()
            return True
        glib.io_add_watch(fd, glib.IO_IN, handle_watch)
    except Exception as ex:
        sendnotification("exception while creating watch: %s" % str(ex))

class GovernorTrayiconApp:
    def __init__(self):
        self.icon_freq= 0
        self.config= Config("thegovernor", { "enforce": False, "apply_at_startup": False } )
        self.governor_globspec= "/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
        self.governor_paths= glob.glob(self.governor_globspec)

        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors") as f:
            self.available_governors= f.readline().split()
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") as f:
            self.selected_governor= f.readline().strip()
            
        # create watch for scaling_governor sysfs file for cpu0 so we get notified of changes
        def cb(path):
            with open(path) as f:
                governor= f.readline().strip()
            if governor!=self.selected_governor:
                time.sleep(0.25)
                if self.config.get("enforce"):
                    gov= self.selected_governor
                    self.selected_governor= governor
                    self.activate_governor(gov)
                else:
                    index= self.available_governors.index(governor)
                    self.governor_items[index].activate()
                    self.update_icon()
                sendnotification("'%s' governor active" % self.selected_governor)
        add_watch(self.governor_paths[0], cb)

        self.tray= gtk.StatusIcon()
        self.tray.set_visible(True)
        self.tray.connect('popup-menu', self.on_popup_menu)
        self.tray.connect('activate', self.on_activate)
        self.menu= self.make_menu()

        cfg_governor= self.config.get("governor")
        if cfg_governor and cfg_governor!=self.selected_governor and self.config.get("apply_at_startup"):
            try:
                self.governor_items[self.available_governors.index(cfg_governor)].activate()
                sendnotification("'%s' governor active" % self.selected_governor)
            except Exception as ex:
                print str(ex)
    
        self.update_icon()
        def cb(): 
            self.update_icon()
            return True
        glib.timeout_add(1000, cb)
        
    def set_dynicon(self, text):
        window= gtk.OffscreenWindow()
        label= gtk.Label()
        label.set_justify(gtk.JUSTIFY_CENTER)
        label.set_markup(text)
        eb= gtk.EventBox()
        eb.add(label)
        #~ eb.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse('green')) # xxxx no effect?
        window.add(eb)
        def draw_complete_event(window, event, statusIcon=self.tray):
            statusIcon.set_from_pixbuf(window.get_pixbuf())
        window.connect("damage-event", draw_complete_event)
        window.show_all()
        
    def set_autostart(self, value):
        self.config.set("autostart", value)
        autostartpath= os.path.join(glib.get_user_config_dir(), "autostart", "thegovernor.desktop")
        scriptpath= os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), sys.argv[0])
        entry= """[Desktop Entry]
Encoding=UTF-8
Version=0.9.4
Type=Application
Name=thegovernor
Comment=
Exec=python %s
Hidden=%s\n""" % (scriptpath, "false" if value else "true")
        with open(autostartpath, "w") as f:
            f.write(entry)
        
    def make_menu(self):
        menu= gtk.Menu()
        item= None
        self.governor_items= []
        for governor in self.available_governors:
            item= gtk.RadioMenuItem(item, governor)
            if(governor == self.selected_governor):
                item.activate()
            item.connect('activate', lambda widget: self.activate_governor(widget.get_label()))
            item.show()
            menu.append(item)
            self.governor_items.append(item)
        item= gtk.SeparatorMenuItem()
        item.show()
        menu.append(item)
        
        item= gtk.CheckMenuItem("Enforce")
        item.set_tooltip_text("Enforce your choice when some other program (e.g. Power Manager) selects another governor.  Requires the python 'inotifyx' package.")
        item.set_active(self.config.get("enforce"))
        item.connect('activate', lambda widget: self.config.set("enforce", widget.get_active()))
        item.show()
        menu.append(item)
        
        item= gtk.CheckMenuItem("Apply at Startup")
        item.set_tooltip_text("Apply your choice when app starts.")
        item.set_active(self.config.get("apply_at_startup"))
        item.connect('activate', lambda widget: self.config.set("apply_at_startup", widget.get_active()))
        item.show()
        menu.append(item)
        
        item= gtk.CheckMenuItem("Autostart")
        #~ item.set_tooltip_text(".")
        item.set_active(bool(self.config.get("autostart")))
        item.connect('activate', lambda widget: self.set_autostart(widget.get_active()))
        item.show()
        menu.append(item)
        
        item= gtk.SeparatorMenuItem()
        item.show()
        menu.append(item)
        quit= gtk.MenuItem("Quit")
        quit.show()
        quit.connect('activate', gtk.main_quit)
        menu.append(quit)
        return menu

    def on_popup_menu(self, icon, event_button, event_time):
        self.show_menu(event_button, event_time)
    
    def on_activate(self, status_icon):
        #~ self.show_menu(1, 0)
        pass
    
    def get_max_freq(self):
        max= 0
        for path in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"):
            with open(path) as f:
                khz= int(f.readline().strip())
                if khz>max: max= khz
        return max
    
    def update_icon(self):
        maxfreq= self.get_max_freq()
        if maxfreq != self.icon_freq:
            self.set_dynicon("<small>%3.1f\nGhz</small>" % (float(self.get_max_freq())/1000000) )
            self.icon_freq= maxfreq
        self.tray.set_tooltip("active governor: %s\n%d cores @ %3.1f GHz max" % 
            (self.selected_governor, len(self.governor_paths), float(maxfreq)/1000000))
    
    def activate_governor(self, governor):
        if self.selected_governor!=governor:
            self.selected_governor= governor
            cmdstr= 'gksudo "bash -c \'echo %s | tee %s\'"' % (governor, self.governor_globspec)
            subprocess.Popen(cmdstr, shell=True)
            self.update_icon()
        self.config.set("governor", governor)
        self.config.sync()
    
    def show_menu(self, event_button, event_time):
        self.menu.popup(None, None, gtk.status_icon_position_menu,
                   event_button, event_time, self.tray)

if __name__=='__main__':
    app= GovernorTrayiconApp()
    gtk.main()

