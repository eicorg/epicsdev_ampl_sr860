"""EPICS PVAccess server for the SR860 lock-in amplifier."""
# pylint: disable=invalid-name
__version__ = 'v0.1.0 2026-10-15'

import argparse
import sys
import time
from threading import Lock

import pyvisa as visa
from pyvisa.errors import VisaIOError

from epicsdev import epicsdev as edev

DEVICE = 'template:'
SENSITIVITIES = (
    '1 V / 1 uA', '500 mV / 500 nA', '200 mV / 200 nA', '100 mV / 100 nA',
    '50 mV / 50 nA', '20 mV / 20 nA', '10 mV / 10 nA', '5 mV / 5 nA',
    '2 mV / 2 nA', '1 mV / 1 nA', '500 uV / 500 pA', '200 uV / 200 pA',
    '100 uV / 100 pA', '50 uV / 50 pA', '20 uV / 20 pA', '10 uV / 10 pA',
    '5 uV / 5 pA', '2 uV / 2 pA', '1 uV / 1 pA', '500 nV / 500 fA',
    '200 nV / 200 fA', '100 nV / 100 fA', '50 nV / 50 fA',
    '20 nV / 20 fA', '10 nV / 10 fA', '5 nV / 5 fA', '2 nV / 2 fA',
    '1 nV / 1 fA',
)
TIME_CONSTANTS = (
    '1 us', '3 us', '10 us', '30 us', '100 us', '300 us', '1 ms', '3 ms',
    '10 ms', '30 ms', '100 ms', '300 ms', '1 s', '3 s', '10 s', '30 s',
    '100 s', '300 s', '1 ks', '3 ks', '10 ks', '30 ks',
)
FILTER_SLOPES = ('6 dB/oct', '12 dB/oct', '18 dB/oct', '24 dB/oct')


class C_:
    """Container for shared device and server state."""

    pargs = None
    dev = None
    resource_manager = None
    pv_commands = {}
    io_lock = Lock()


def myPVDefs():
    """Return the PV definitions for the SR860."""
    F, T, U, LL, LH = 'features', 'type', 'units', 'limitLow', 'limitHigh'
    SET = 'setter'
    pv_defs = [
        ['visaResource', 'VISA resource used to access the instrument',
         C_.pargs.resource],
        ['idn', 'Instrument identification (*IDN?)', ''],
        ['dateTime', 'Server local date/time', 'N/A'],
        ['pollCount', 'Number of measurement poll cycles', 0, {T: 'u32'}],
        ['x', 'In-phase output (X), units follow the input mode', 0.0, {U: 'V/A'}],
        ['y', 'Quadrature output (Y), units follow the input mode', 0.0, {U: 'V/A'}],
        ['r', 'Magnitude output (R), units follow the input mode', 0.0, {U: 'V/A'}],
        ['theta', 'Phase output (theta)', 0.0, {U: 'deg'}],
        ['frequency', 'Internal reference frequency', 1000.0,
         {F: 'W', U: 'Hz', LL: 0.001, LH: 500000.0, SET: set_scpi}],
        ['phase', 'Reference phase', 0.0,
         {F: 'W', U: 'deg', LL: -360.0, LH: 360.0, SET: set_scpi}],
        ['referenceMode', 'Reference source',
         ['Internal', 'External', 'Dual', 'Chopper'],
         {F: 'WD', SET: set_scpi}],
        ['inputMode', 'Input amplifier mode', ['Voltage', 'Current'],
         {F: 'WD', SET: set_scpi}],
        ['inputConfig', 'Voltage input configuration', ['A', 'A-B'],
         {F: 'WD', SET: set_scpi}],
        ['inputCoupling', 'Voltage input coupling', ['AC', 'DC'],
         {F: 'WD', SET: set_scpi}],
        ['inputGround', 'Voltage input shield grounding', ['Float', 'Ground'],
         {F: 'WD', SET: set_scpi}],
        ['sensitivity', 'Sensitivity setting (voltage/current), SCAL',
         list(SENSITIVITIES), {F: 'WD', SET: set_scpi}],
        ['timeConstant', 'Output filter time constant',
         list(TIME_CONSTANTS), {F: 'WD', SET: set_scpi}],
        ['filterSlope', 'Output filter slope', list(FILTER_SLOPES),
         {F: 'WD', SET: set_scpi}],
        ['syncFilter', 'Synchronous filter', ['Off', 'On'],
         {F: 'WD', SET: set_scpi}],
        ['sineAmplitude', 'Sine output amplitude', 0.1,
         {F: 'W', U: 'V', LL: 1e-9, LH: 2.0, SET: set_scpi}],
        ['instrCmdS', 'Execute a raw SR860 command', '*IDN?',
         {F: 'W', SET: set_instrCmdS}],
        ['instrCmdR', 'Response to instrCmdS', ''],
        ['autoPhase', 'Run the SR860 auto-phase function', ['Idle', 'Run'],
         {F: 'WD', SET: set_auto_phase}],
    ]
    return pv_defs


def _local_pv_name(pv):
    """Return a PV suffix from the callback PV object."""
    return str(pv.name).rsplit(':', 1)[-1]


def device_command(command):
    """Send a command and return its response for queries."""
    edev.printv(f'>SR860: {command}')
    try:
        with C_.io_lock:
            if '?' in command:
                return C_.dev.query(command).strip()
            C_.dev.write(command)
            return ''
    except VisaIOError as exc:
        edev.printe(f'SR860 VISA error for {command}: {exc}')
    return None


def set_scpi(value, pv, *_):
    """Write a PV-associated SR860 command."""
    pv_name = _local_pv_name(pv)
    mapping = C_.pv_commands.get(pv_name)
    if mapping is None:
        edev.printe(f'No SR860 command mapping for PV {pv_name}')
        return

    command_value = value
    options = mapping.get('options')
    if options is not None:
        try:
            index = options.index(str(value))
        except ValueError:
            edev.printe(f'Invalid value {value!r} for PV {pv_name}')
            return
        enum_values = mapping.get('enum_values')
        command_value = enum_values[index] if enum_values is not None else index
    suffix = mapping.get('suffix', '')
    if mapping.get('numeric', False):
        try:
            command_value = float(value)
        except (TypeError, ValueError):
            edev.printe(f'Invalid numeric value {value!r} for PV {pv_name}')
            return
    if device_command(f'{mapping["command"]} {command_value}{suffix}') is None:
        return
    edev.publish(pv_name, value)


def set_instrCmdS(command, *_):
    """Send a raw instrument command and publish any query response."""
    command = str(command).strip()
    edev.publish('instrCmdR', '')
    response = device_command(command)
    if response is not None:
        edev.publish('instrCmdR', response)


def set_auto_phase(value, *_):
    """Run auto-phase when requested and return the action PV to Idle."""
    if str(value) == 'Run':
        if device_command('APHS') is not None:
            edev.publish('autoPhase', 'Idle')


def build_command_map():
    """Create a mapping from PV suffixes to command metadata."""
    commands = {
        'frequency': {'command': 'FREQINT', 'numeric': True, 'suffix': ' HZ'},
        'phase': {'command': 'PHAS', 'numeric': True, 'suffix': ' DEG'},
        'referenceMode': {
            'command': 'RSRC', 'options': ['Internal', 'External', 'Dual', 'Chopper'],
            'values': ['INT', 'EXT', 'DUAL', 'CHOP'],
        },
        'inputMode': {
            'command': 'IVMD', 'options': ['Voltage', 'Current'],
            'values': ['VOLT', 'CURR'],
        },
        'inputConfig': {'command': 'ISRC', 'options': ['A', 'A-B']},
        'inputCoupling': {
            'command': 'ICPL', 'options': ['AC', 'DC'], 'values': ['AC', 'DC'],
        },
        'inputGround': {
            'command': 'IGND', 'options': ['Float', 'Ground'],
            'values': ['FLO', 'GRO'],
        },
        'sensitivity': {'command': 'SCAL', 'options': list(SENSITIVITIES)},
        'timeConstant': {'command': 'OFLT', 'options': list(TIME_CONSTANTS)},
        'filterSlope': {'command': 'OFSL', 'options': list(FILTER_SLOPES)},
        'syncFilter': {
            'command': 'SYNC', 'options': ['Off', 'On'], 'values': ['OFF', 'ON'],
        },
        'sineAmplitude': {'command': 'SLVL', 'numeric': True, 'suffix': ' V'},
    }
    for pv_name, metadata in commands.items():
        if 'values' in metadata:
            metadata['enum_values'] = metadata.pop('values')
        elif 'options' in metadata and not metadata.get('numeric'):
            metadata['enum_values'] = [str(index) for index in range(len(metadata['options']))]
        C_.pv_commands[pv_name] = metadata


def _read_enum(pv_name, response):
    """Translate a numeric enum response to its PV display value."""
    metadata = C_.pv_commands[pv_name]
    options = metadata['options']
    try:
        index = int(response)
        value = options[index]
    except (ValueError, IndexError):
        edev.printe(f'Unexpected response {response!r} for {metadata["command"]}?')
        return
    edev.publish(pv_name, value, ifChanged=True)


def read_settings():
    """Read the current front-panel settings into their corresponding PVs."""
    for pv_name, metadata in C_.pv_commands.items():
        response = device_command(f'{metadata["command"]}?')
        if response is None:
            continue
        if 'options' in metadata:
            _read_enum(pv_name, response)
            continue
        try:
            value = float(response)
        except ValueError:
            edev.printe(
                f'Unexpected response {response!r} for {metadata["command"]}?'
            )
            continue
        edev.publish(pv_name, value, ifChanged=True)
    edev.publish('dateTime', time.strftime('%Y-%m-%d %H:%M:%S'), ifChanged=True)


def _read_snap(command, pv_names):
    """Read and publish a synchronized group of measurement values."""
    response = device_command(command)
    if response is None:
        return
    values = response.split(',')
    if len(values) != len(pv_names):
        edev.printe(f'Unexpected response {response!r} for {command}')
        return
    try:
        parsed = [float(value.strip()) for value in values]
    except ValueError:
        edev.printe(f'Invalid numeric response {response!r} for {command}')
        return
    for pv_name, value in zip(pv_names, parsed):
        edev.publish(pv_name, value, ifChanged=True)


def poll():
    """Poll synchronized lock-in measurements."""
    _read_snap('SNAP? X,Y', ('x', 'y'))
    _read_snap('SNAP? R,THETA', ('r', 'theta'))
    edev.publish('pollCount', edev.pvv('pollCount') + 1)


def periodic_update():
    """Refresh instrument settings that may have changed on the front panel."""
    read_settings()


def init_visa(resource):
    """Open the VISA instrument and validate its identity."""
    edev.printi(f'Opening VISA resource {resource}')
    try:
        C_.resource_manager = visa.ResourceManager()
        C_.dev = C_.resource_manager.open_resource(
            resource,
            timeout=3000,
            read_termination='\n',
            write_termination='\n',
        )
        idn = device_command('*IDN?')
    except (VisaIOError, OSError, ValueError, ModuleNotFoundError) as exc:
        edev.printe(f'Could not open VISA resource {resource}: {exc}')
        sys.exit(1)
    if not idn:
        edev.printe(f'No instrument identification response from {resource}')
        sys.exit(1)
    if 'SR860' not in idn.upper():
        edev.printe(f'Connected instrument is not an SR860: {idn}')
        sys.exit(1)
    edev.publish('idn', idn)
    edev.printi(f'SR860 IDN: {idn}')


def serverStateChanged(newState: str):
    """Handle server state transitions."""
    if newState == 'Start':
        edev.printi('Start requested')
        read_settings()
    elif newState == 'Stop':
        edev.printi('Stop requested')
    elif newState == 'Exit':
        edev.printi('Exit requested')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=f'{__version__}, epicsdev:{edev.__version__}',
    )
    parser.add_argument('-a', '--autosave', nargs='?', default='', help=
        'Autosave control. If omitted, autosave is enabled with default directory.')
    parser.add_argument('-c', '--recall', action='store_false', help=
        'If given: do not restore initial PV values from autosave cache.')
    parser.add_argument('-i', '--instance', default='0', help='Device instance.')
    parser.add_argument('-p', '--putlogPV', nargs='?', default='', help=
        'PV name for logging put operations. Empty means default putlog:dump.')
    parser.add_argument('-r', '--resource', required=True, help=
        'VISA resource string for the SR860.')
    parser.add_argument('-v', '--verbose', action='count', default=0, help=
        'Increase verbosity (-vv for more).')
    parser.add_argument('device', nargs='?', default=DEVICE, help=
        'Device name, the prefix for all generated PVs <prefix><instance>:')

    C_.pargs = parser.parse_args()
    if C_.pargs.putlogPV == '':
        C_.pargs.putlogPV = 'putlog:dump'
    C_.pargs.prefix = f'{C_.pargs.device}{C_.pargs.instance}:'

    C_.PvDefs = myPVDefs()
    build_command_map()
    PVs = edev.init_epicsdev(
        C_.pargs.prefix,
        C_.PvDefs,
        C_.pargs.verbose,
        serverStateChanged,
        None,
        C_.pargs.autosave,
        C_.pargs.recall,
        C_.pargs.putlogPV,
    )
    init_visa(C_.pargs.resource)
    print(f'Using PV prefix: {C_.pargs.prefix}')

    edev.publish('VERSION', __version__)
    edev.set_server('Start')
    server = edev.Server(providers=[PVs])
    edev.printi((f'Server for {C_.pargs.prefix} started. Sleeping per cycle: '
                 f'{repr(edev.pvv("sleep"))} S.'))

    try:
        while True:
            state = edev.serverState()
            if state.startswith('Exit'):
                break
            if not state.startswith('Stop'):
                poll()
            if not edev.sleep():
                periodic_update()
    except KeyboardInterrupt:
        edev.printi('Keyboard interrupt received, exiting main loop...')
        edev.set_server('Exit')
    except OSError as exc:
        edev.printe(f'Operating system error in server loop: {exc}')

    if C_.dev is not None:
        C_.dev.close()
    if C_.resource_manager is not None:
        C_.resource_manager.close()
    edev.printi('Server is exited')
