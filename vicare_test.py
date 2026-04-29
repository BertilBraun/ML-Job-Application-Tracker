import sys
import logging
from PyViCare.PyViCare import PyViCare, DictWrap

client_id = '9ee7307fa4f36d8663a50df181085968'
email = 'braun_oliver@gmx.de'
password = 'D!57gpA8(873'

vicare = PyViCare()
vicare.initWithCredentials(email, password, client_id, 'token.save')
device = vicare.devices[0]
for device in vicare.devices:
    print(device.getModel(), 'Online' if device.isOnline() else 'Offline', device.getDeviceType())

ins: list = vicare.installations

for e in ins:
    print(e.__dict__)

t = device.asHeatPump()
# print(t.getActiveMode())
# print(t.getDomesticHotWaterConfiguredTemperature())
# print(t.getDomesticHotWaterStorageTemperature())
# print(t.getOutsideTemperature())
# print(t.getRoomTemperature())
# print(t.getBoilerTemperature())
# print(t.setDomesticHotWaterTemperature(59))

exit()

circuit = t.circuits[0]  # select heating circuit

print(circuit.getSupplyTemperature())
print(circuit.getHeatingCurveShift())
print(circuit.getHeatingCurveSlope())

print(circuit.getActiveProgram())
print(circuit.getPrograms())

print(circuit.getCurrentDesiredTemperature())
print(circuit.getDesiredTemperatureForProgram('comfort'))
print(circuit.getActiveMode())

print(circuit.getDesiredTemperatureForProgram('comfort'))
print(circuit.setProgramTemperature('comfort', 21))
print(circuit.activateProgram('comfort'))
print(circuit.deactivateComfort())

burner = t.burners[0]  # select burner
print(burner.getActive())

compressor = t.compressors[0]  # select compressor
print(compressor.getActive())
