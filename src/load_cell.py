from time import sleep

import hx711


class LoadCell(hx711.HX711):
    def __init__(self, data_pin: int, clock_pin: int, gain: int=128, channel: str='A'):
        super().__init__(data_pin, clock_pin, gain, channel)
        self.offset = 0

    def tare(self, sample_size: int=25):
        readings = self.get_raw_data(sample_size)

        average_val = sum(readings) / len(readings)
        self.offset = average_val

    def take_measurement(self) -> float:
        measurement = sum(self.get_raw_data(3)) / 3
        measurement -= self.offset
        return measurement

    def calibrate(self) -> None:
        calibrating = True
        input("Ensure that 0 mass is on the scale, then press enter.")
        working_mass = 0

        calibration_data = [[],[]]

        for i in range(10):
            calibration_data[0].append(self.take_measurement())
            calibration_data[1].append(working_mass)

        while calibrating:
            working_mass_accepted = False

            while not working_mass_accepted:
                try:
                    working_mass = int(input("Add a known mass onto the scale.\nMass: "))
                    working_mass_accepted = True
                except Exception:
                    print("Not a valid mass...")

            print("Do not disturb the scale during meausurement...")
            for i in range(10):
                calibration_data[0].append(self.take_measurement())
                calibration_data[1].append(working_mass)

            if input("Do you wish to continue? [Y/N] ") == "N":
                calibrating = False

        for i in range(len(calibration_data[0])):
            print(calibration_data[0][i], calibration_data[1][i], sep='---')


def main():
    cell = LoadCell(12, 23)
    sleep(1)
    while True:
        input("Press the enter key to continue...")
        for i in range(10):
            print(i, str(cell.take_measurement()))
        sleep(2)


if __name__ == '__main__':
    main()