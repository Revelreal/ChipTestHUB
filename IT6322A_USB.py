# -*- coding: utf-8 -*-

import pyvisa


class drivers:
    def __init__(self, resource_address: str):
        self.resource_address = resource_address
        self.instrument = None
        self._connect()

    def _connect(self):
        rm = pyvisa.ResourceManager()
        try:
            self.instrument = rm.open_resource(self.resource_address)
            self.instrument.timeout = 5000
        except Exception as e:
            raise ConnectionError(f"无法连接电源 {self.resource_address}: {e}")

    def Enter_Remote(self):
        self.instrument.write("SYST:REM")

    def TunrOn_Output(self):
        self.instrument.write("OUTP ON")

    def TurnOff_Output(self):
        self.instrument.write("OUTP OFF")

    def Set_OutputVolt_CH1(self, voltage: float):
        self.instrument.write(f"VOLT {voltage}")

    def Set_OutputCurr_CH1(self, current: float):
        self.instrument.write(f"CURR {current}")

    def Get_OutputVolt_CH1(self) -> float:
        return float(self.instrument.query("VOLT?"))

    def Get_OutputCurr_CH1(self) -> float:
        return float(self.instrument.query("CURR?"))

    def Get_MeasuredVolt_CH1(self) -> float:
        return float(self.instrument.query("MEAS:VOLT?"))

    def Get_MeasuredCurr_CH1(self) -> float:
        return float(self.instrument.query("MEAS:CURR?"))

    def close(self):
        if self.instrument:
            self.instrument.close()
