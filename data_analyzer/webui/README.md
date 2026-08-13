# DBQ Admin Web UI

A Flask-based web administration panel for the DaughterBoard Qualification (DBQ) script operations.

## Features

- **Authentication**: Login using the same credentials as the main web_ui system (MySQL/MariaDB authentication)
- **Run DBQ Script**: Execute DBQ_Mk6.py with various parameters:
  - Regeneration modes (all, benchtest_id_log, benchtest_id_results_log, plots)
  - Specific benchtest IDs (single ID or range)
  - Specific daughterboard ID filtering
- **Edit Configuration**: Modify vars.yaml parameters through a web interface
- **View Configuration**: Read-only view of current vars.yaml configuration

## Installation

1. Ensure Python 3 and required packages are installed:
```bash
pip install flask mysql-connector-python ruamel.yaml
```

2. The web UI is located in `data_analyzer/webui/`

## Running the Application

Start the Flask server:

```bash
cd /root/atlas_lab_scripts/data_analyzer/webui
python3 app.py
```

The application will run on `http://127.0.0.1:5001`

## Usage

1. **Login**: Access the web UI and login with your database credentials
   - Username: Your MySQL/MariaDB username
   - Password: Your MySQL/MariaDB password
   - Development Database: Optional checkbox to use development database instead of production

2. **Dashboard**: Main panel with navigation to all features

3. **Run Script**: 
   - Select regeneration mode (optional)
   - Enter specific benchtest IDs (optional, supports single ID or range like "1-5")
   - Enter specific daughterboard ID (optional)
   - Click "Run Script" to execute DBQ_Mk6.py

4. **Edit Configuration**:
   - Navigate to Edit Configuration
   - Modify parameter values as needed
   - For list values, use format: `[value1, value2]`
   - Click "Save Configuration" to update vars.yaml

5. **View Configuration**:
   - Read-only view of current vars.yaml settings
   - Useful for reference without editing

## File Structure

```
webui/
├── app.py              # Main Flask application
├── templates/          # HTML templates
│   ├── login.html      # Login page
│   ├── dashboard.html  # Main dashboard
│   ├── run_script.html # Script execution interface
│   ├── edit_vars.html  # Configuration editor
│   └── view_vars.html  # Configuration viewer
└── README.md          # This file
```

## Security Notes

- The application uses the same authentication system as the main web_ui
- Credentials are stored in session (not in plain text)
- The secret key should be changed in production environments
- The application runs on localhost by default

## Database Connection

The web UI connects to the same MariaDB database as the main web_ui:
- Production database: `tiledb`
- Development database: `tiledbdev`
- Host: `piro-atlas-lab-vserver-01.fysik.su.se`

## Troubleshooting

**Script execution fails**: 
- Check that DBQ_Mk6.py has execute permissions
- Verify the script path in app.py is correct
- Check the script output for specific errors

**Cannot save configuration**:
- Ensure vars.yaml has write permissions
- Check that the YAML syntax is valid after editing

**Login fails**:
- Verify database credentials are correct
- Check database connectivity
- Ensure the database server is accessible
