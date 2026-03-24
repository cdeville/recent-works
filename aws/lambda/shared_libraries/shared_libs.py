# Shared Libraries
from logging_utils import setup_logging
logger = setup_logging()


def get_secret(secret_name):
    """
    Retrieve a secret from AWS Secrets Manager.

    Args:
        secret_name (str): The name or ARN of the secret in AWS Secrets Manager.

    Returns:
        dict or str: The secret value as a dictionary (if parseable) or as a
                     plain string (if plaintext).

    Raises:
        RuntimeError: If the secret_name parameter is not provided or is empty.
        Exception: If the secret cannot be retrieved from AWS Secrets Manager.

    Example:
        >>> secret = get_secret('my-database-credentials')
        >>> # Returns {'username': 'admin', 'password': 'secret123'}
    """
    import ast
    import boto3

    # Validate the secret name parameter
    if not secret_name:
        logger.error("Passed parameter environment variable is not set")
        raise RuntimeError("Passed parameter environment variable is required")
    logger.info("Using passed envar secret name: %s", secret_name)

    try:
        secrets = boto3.client('secretsmanager')
        response = secrets.get_secret_value(SecretId=secret_name)
        secret_str = response["SecretString"]
        logger.info("Successfully retrieved from Secrets Manager")
        try:
            # Try to parse secret as Python literal dict/list (key/value format)
            return ast.literal_eval(secret_str)
        except (ValueError, SyntaxError):
            # If parsing fails, treat it as plaintext
            return secret_str
    except Exception as e:
        logger.error("Failed to retrieve from Secrets Manager: %s", e, exc_info=True)
        raise


def get_formatted_datetime(with_time: bool = False) -> str:
    """
    Return a nicely formatted current date & time for naming.

    Returns the current date or datetime formatted using only hyphens for
    AWS naming compatibility.

    Args:
        with_time (bool, optional): If True, include time in the format.
                                    If False, return only the date.
                                    Defaults to False.

    Returns:
        str: The formatted date or datetime string.
             - 'Jun-27-2025' if with_time is False
             - 'Jun-27-2025-07-42-05' if with_time is True

    Example:
        >>> get_formatted_datetime()
        'Nov-20-2025'
        >>> get_formatted_datetime(with_time=True)
        'Nov-20-2025-14-30-45'
    """
    from datetime import datetime

    now = datetime.now()
    if with_time:
        return now.strftime("%b-%d-%Y-%H-%M-%S")
    else:
        return now.strftime("%b-%d-%Y")


def connect_mysql(dbsecret, host='', port=''):
    """
    Connect to a MySQL database using credentials from AWS Secrets Manager.

    Args:
        dbsecret (str): The name of the secret in AWS Secrets Manager containing
                        database credentials (must include 'user', 'password',
                        'host', and optionally 'port').
        host (str, optional): Override host from the secret. If provided, this
                              host will be used instead of the one in the secret.
                              Defaults to ''.
        port (str or int, optional): Override port from the secret. If provided,
                                     this port will be used instead of the one in
                                     the secret. Defaults to ''.

    Returns:
        mysql.connector.connection.MySQLConnection: An active database connection
                                                     with autocommit enabled.

    Raises:
        RuntimeError: If dbsecret parameter is not provided or is empty.
        Exception: If credentials cannot be retrieved from Secrets Manager.
        mysql.connector.Error: If the database connection fails.

    Example:
        >>> conn = connect_mysql('mysql')
        >>> cursor = conn.cursor()
        >>> cursor.execute("SELECT * FROM insert_schema_table;")
    """
    import mysql.connector

    # 1. Grab the secret name
    secret_name = dbsecret
    if not secret_name:
        logger.error("Environment variable DbSecretName is not set")
        raise RuntimeError("DbSecretName environment variable is required")
    logger.info("Using secret name: %s", secret_name)

    # 2. Fetch credentials from Secrets Manager
    try:
        db_cred = get_secret(secret_name)
        logger.info("Successfully retrieved database credentials")
    except Exception as e:
        logger.error("Failed to retrieve DB credentials: %s", e, exc_info=True)
        raise

    # 3. Connect to MySQL/MariaDB
    if not port:
        port = int(db_cred.get("port", 3306))
    else:
        port = int(port)
    if host:
        try:
            conn = mysql.connector.connect(
                user=db_cred["user"],
                password=db_cred["password"],
                host=host,
                port=port,
                autocommit=True
            )
            logger.info("Database connection established to host %s:%s", host, port)
            return conn
        except mysql.connector.Error as err:
            logger.error("Database connection failed: %s", err, exc_info=True)
            raise
    else:
        try:
            conn = mysql.connector.connect(
                user=db_cred["user"],
                password=db_cred["password"],
                host=db_cred["host"],
                port=port,
                autocommit=True
            )
            logger.info("Database connection established to host %s:%s", db_cred["host"], port)
            return conn
        except mysql.connector.Error as err:
            logger.error("Database connection failed: %s", err, exc_info=True)
            raise


def get_ssm_parameter(paramname):
    """
    Retrieve the value of an SSM Parameter Store entry.

    Args:
        paramname: the full path/name of the parameter (e.g. "/my/service/config")

    Returns:
        the parameter's string value

    Raises:
        ClientError: if the parameter doesn't exist or you lack permissions

    Example:
        >>> value = get_ssm_parameter(INSERT_ENV_VAR_PARAM)
    """

    from botocore.exceptions import ClientError
    import boto3

    # Create the SSM Client Session
    ssm = boto3.client('ssm')

    # Fetch and return the value
    try:
        response = ssm.get_parameter(Name=paramname)
        logger.debug(f"Getting Parameter Store Value for {paramname}")
        return response['Parameter']['Value']
    except ClientError as e:
        logger.error(f"Error: {e}")
        raise


def write_str_to_temp_file(string: str) -> str:
    """
    Writes a string (cert, key, etc) to a temporary file and returns its path.

    Args:
        string (str): The string content to write.
    Returns:
        str: Path to the created temporary file.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, mode='w') as file:
        file.write(string)
        return file.name


