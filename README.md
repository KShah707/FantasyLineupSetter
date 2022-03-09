# FantasyLineupSetter
Automated tools to manage private Yahoo fantasy hockey team

## Setup Directions:
0. Obtain credentials from the Yahoo API which uses the OAuth protocol
    * Create a Yahoo account and set up credentials for the Fantasy Sports API: https://developer.yahoo.com/fantasysports/guide/
    * `pip install yahoo_oauth`
    * Follow the directions in https://github.com/josuebrunel/yahoo-oauth to save permanent credentials in a file `oauth_key.json` which can be reused without manual login each time
1. From inside the project's root directory, run the following commands to download Python dependencies and package them for deployment
```
pip install --target ./dependencies  -r requirements.txt
cd dependencies
zip -r ../deployment-package.zip .
cd ..
zip -g deployment-package.zip fantasy_lineup_setter.py
zip -g deployment-package.zip oauth_key.json
```
2. Create an AWS Lambda function and upload this zipfile as the function source code
3. Change the function configurations
    * Set timeout to 15 seconds
    * Set handler to `fantasy_lineup_setter.set_lineup_handler`
4. Create an AWS EventBridge Rule to invoke the function once / day
    * Cron expression: `0 13 1/1 * ? *` (daily at 8am ET / 1pm GMT)

See https://docs.aws.amazon.com/lambda/latest/dg/python-package.html for additional help