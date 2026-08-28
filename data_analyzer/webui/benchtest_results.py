"""Helpers for reading benchtest result files."""

from pathlib import Path


def get_failed_tests_for_serial(serial, benchtest_id, drive_dir="/var/www/html/drive/benchtests/"):
    """
    Read benchtest CSV file and extract failed tests for a specific serial number.

    Returns:
        tuple: (list of failed test names or None, board_pass_fail value or None)
    """
    benchtest_folder = f"benchtest_id_{benchtest_id}"
    csv_file = Path(drive_dir) / benchtest_folder / f"{benchtest_folder}_results.csv"

    if not csv_file.exists():
        return None, None

    try:
        with open(csv_file, 'r') as file_handle:
            lines = file_handle.readlines()

        header = lines[0].strip().split(',')
        if len(header) < 2:
            return None, None

        serial_str = str(serial)
        serial_index = None
        for index, column in enumerate(header[1:], start=1):
            if str(column) == serial_str:
                serial_index = index
                break

        if serial_index is None:
            return None, None

        failed_tests = []
        board_pass_fail = None
        for line in lines[1:]:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split(',')
            if len(parts) <= serial_index:
                continue

            measurement = parts[0]
            value = parts[serial_index].strip()

            if measurement == 'Board PassFail':
                board_pass_fail = value

            if value == '0' and measurement not in ['burned', 'Board PassFail']:
                failed_tests.append(measurement)

        return (failed_tests if failed_tests else None), board_pass_fail

    except Exception as error:
        print(f"Error reading CSV file {csv_file}: {error}")
        return None, None
