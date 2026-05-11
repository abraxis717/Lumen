#!/usr/bin/env python3
import fcntl
import os
import struct
import time
import psutil
import signal
import sys
import requests
from datetime import datetime

KERNEL_DEVICE = '/dev/cathedral'
IOCTL_STEP = 0x4301
IOCTL_GET_STATUS = 0x80284303
OLLAMA_URL = 'http://localhost:11434/api/generate'
MODEL = 'tinyllama'
UPDATE_INTERVAL = 30

class TimeEater:
    def __init__(self):
        self.running = True
        self.last_cpu = None
        self.hebbian_delta = 0.0
        self.cpu_history = []
        signal.signal(signal.SIGINT, self.signal_handler)
    
    def signal_handler(self, sig, frame):
        self.running = False
    
    def read_kernel(self):
        try:
            fd = os.open(KERNEL_DEVICE, os.O_RDWR)
            fcntl.ioctl(fd, IOCTL_STEP)
            buf = bytearray(40)
            fcntl.ioctl(fd, IOCTL_GET_STATUS, buf, True)
            result = struct.unpack('<Q I B 3x I I Q Q', buf[:40])
            os.close(fd)
            return result[1], result[4], result[5] / (1024**3), result[6]
        except:
            return 0, 0, 0, 0
    
    def get_temp(self):
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                return int(f.read().strip()) / 1000.0
        except:
            return 0.0
    
    def update_hebbian(self, cpu):
        if self.last_cpu is not None:
            change = abs(cpu - self.last_cpu)
            self.hebbian_delta = self.hebbian_delta * 0.9 + change * 0.1
        self.last_cpu = cpu
        self.cpu_history.append(cpu)
        if len(self.cpu_history) > 10:
            self.cpu_history.pop(0)
        return self.hebbian_delta
    
    def get_trend(self):
        if len(self.cpu_history) < 2:
            return "→"
        first = self.cpu_history[0]
        last = self.cpu_history[-1]
        if last - first > 5:
            return "↑"
        elif first - last > 5:
            return "↓"
        else:
            return "→"
    
    def get_inference(self, cpu, mem, hebbian, temp):
        prompt = f"""CPU: {cpu:.1f}% MEM: {mem:.1f}GB HEBBIAN: {hebbian:.1f} TEMP: {temp:.1f}°C
One sentence status and one sentence optimization:"""
        try:
            resp = requests.post(OLLAMA_URL, json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 80, "temperature": 0.3}
            }, timeout=10)
            return resp.json().get("response", "Stable. No optimization.")
        except:
            return "Stable. No optimization."
    
    def run(self):
        print("\n" + "="*70)
        print("TIME EATER - Unified Controller")
        print("="*70)
        
        while self.running:
            kernel_delta, cpu_raw, mem, slack = self.read_kernel()
            cpu = psutil.cpu_percent()
            temp = self.get_temp()
            hebbian = self.update_hebbian(cpu)
            trend = self.get_trend()
            inference = self.get_inference(cpu, mem, hebbian, temp)
            
            print(f"\n{'='*70}")
            print(f"TIME EATER REPORT - {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*70}")
            print(f"\n  CPU:        {cpu:5.1f}%  {trend}")
            print(f"  MEMORY:     {mem:5.1f} GB")
            print(f"  HEBBIAN:    {hebbian:5.1f}  (plasticity)")
            print(f"  TEMP:       {temp:5.1f}°C")
            print(f"\n  INFERENCE:  {inference}")
            print(f"\n{'='*70}")
            
            time.sleep(UPDATE_INTERVAL)
        
        print("\nTime Eater stopped.")

if __name__ == "__main__":
    eater = TimeEater()
    eater.run()
