""" Place holder for general-purposed methods and classes that interact with Ambiosensing internal MySQL database """

import utils
import ambi_logger
import traceback
import user_config
import mysql.connector as mysqlc
from mysql.connector.errors import Error
import datetime
import os
from ThingsBoard_REST_API import tb_telemetry_controller


# ---------------------------------------------- DATABASE RELATED CUSTOM EXCEPTION ----------------------------------------------------------------------------------------------------------------------------------------------------
class MySQLDatabaseException(Exception):
    message = None
    error_code = None
    sqlstate = None
    stack = None

    def __init__(self, message=None, error_code=None, sqlstate=None):
        """The standard Exception constructor. This exception is tailored after the typical elements that are returned in a SQL related error. Also, due to the intense logging actions undertaken so far in this project,
        its a good idea to use Exceptions that easily expose their error messages (something that is not trivial with BaseException or your run-of-the-mill Exception) so that they can be captured and logged by the logger object
        @:param message (str) - A short description of the reason behind the raising of this Exception
        @:param error_code (int) - The error_code associated with this exception, if any
        @:param sqlstate (str) - The SQL context when the error happened
        @:raise utils.InputValidationException - If this Exception is formed using illegal argument types"""

        sql_except = ambi_logger.get_logger(__name__)

        try:
            if message:
                utils.validate_input_type(message, str)
            if error_code:
                utils.validate_input_type(error_code, int)
            if sqlstate:
                utils.validate_input_type(sqlstate, str)
        except utils.InputValidationException as ive:
            sql_except.error(ive.message)
            raise ive

        self.message = message
        self.error_code = error_code
        self.sqlstate = sqlstate
        self.stack = traceback.format_exc()


# ---------------------------------------------- GENERAL PURPOSE METHODS ----------------------------------------------------------------------------------------------------------------------------------------------------
def connect_db(database_name):
    """Basic method that return a connection object upon a successful connection attempt to a database whose connection data is present in the configuration file, as a dictionary with the database name as its key
    NOTE: This method assumes a single server instance for the installation of all database data (a single triplet hostname, username and password). For databases that spawn over multiple servers or to support more than one user in this
    regard, please change this method accordingly
    @:param database_name (str) - The name of the database to connect to.
    @:raise util.InputValidationException - If the input arguments provided are invalid
    @:raise Exception - For any other occurring errors
    @:return cnx (mysql.connector.connection.MySQLConnection) - An active connection to the database"""
    connect_log = ambi_logger.get_logger(__name__)

    try:
        utils.validate_input_type(database_name, str)
        connection_dict = user_config.mysql_db_access
    except utils.InputValidationException as ive:
        connect_log.error(ive.message)
        raise ive
    except KeyError as ke:
        error_msg = "Missing '{0}' key from the user_config.mysql_db_access dictionary!".format(str(database_name))
        connect_log.error(error_msg)
        raise ke

    try:
        cnx = mysqlc.connect(user=connection_dict['username'],
                             password=connection_dict['password'],
                             host=connection_dict['host'],
                             database=connection_dict['database'])
    except Error as err:
        connect_log.error(err.msg)
        # Catch any errors under a generic 'Error' exception and pass it upwards under a more specific MySQLDatabaseException
        raise MySQLDatabaseException(message=err.msg, error_code=err.errno, sqlstate=err.sqlstate)

    if cnx and cnx.is_connected():
        # Return the connection object if it exists and it is connected to the database
        return cnx
    # This is not supposed to happen, but anyway. Run the next code only in the unlikely event of the connection got to this point without raising any of the expected errors but the connection.is_connected() comes back as False
    else:
        error_msg = "The connection with the database was not established but no errors were raised in the process!"
        connect_log.error(error_msg)
        raise MySQLDatabaseException(message=error_msg)


def get_table_columns(database_name, table_name):
    """This method does a simple SELECT query to the database for just the columns names in a given table. This is particular useful for building INSERT and UPDATE statements that require a specification of these elements on the
    statements
    @:param database (str) - The name of the database to connect to
    @:param table_name (str) - The name of the table from the database to connect to
    @:raise utils.InputValidationException - If any of the inputs is not valid
    @:raise MySQLDatabaseException - for database related exceptions
    @:raise Exception - For any other type of errors
    @:return column_list (list of str) - A list with all the names of the columns, in order, extracted from the database.table_name
    """
    get_table_log = ambi_logger.get_logger(__name__)

    try:
        utils.validate_input_type(database_name, str)
        utils.validate_input_type(table_name, str)

        cnx = connect_db(database_name=database_name)
        select_cursor = cnx.cursor(buffered=True)

        sql_select = """SHOW COLUMNS FROM """ + str(table_name) + """;"""
        select_cursor.execute(sql_select)
        # Executing a SQL statement using the cursor object yields all sorts of useful information. For this particular case I'm interested in the cursor.column_names parameter, which is a n member tuple, n = number of columns in the
        # table targeted by the statement, in which each tuple element is the name of the column in position i. From there is just a matter of casting that parameter into a list (its a direct operation and, overall,
        # I find lists way more friendly to operate than tuples, but that's subjective) and return it back to the caller
        result_list = list(select_cursor.fetchall())

        # The result list is a list of tuples containing the following details: (column_name, data_type, accepts_NULL_values, default_value). Obviously I'm only interested in the column names. So retrieve all the index 0 elements of the tuple list
        # to the return list
        return_list = []
        for tuples in result_list:
            return_list.append(tuples[0])

        return return_list

    except utils.InputValidationException as ive:
        get_table_log.error(__name__)
        raise ive
    except Error as err:
        get_table_log.error(err.msg)
        raise MySQLDatabaseException(message=err.msg, error_code=err.errno, sqlstate=err.sqlstate)
    except TypeError:
        error_msg = "Cannot parse a list from the dictionary of results obtained. Please review the database response format."
        get_table_log.error(error_msg)
        raise MySQLDatabaseException(message=error_msg)


def create_update_sql_statement(column_list, table_name, trigger_column_list):
    """This method automatized the build if standard SQL UPDATE statements. NOTE: This method produces the simplest of SQL UPDATE statements, that is, "UPDATE table_name SET (column_name = %s) WHERE (trigger_column = %s);",
    in which the %s elements are to be replaced by providing the adequate tuple of update values in the statement execution. This means that only one record can be updated given that the trigger condition is an equality. This method is
    not suitable for more complex SQL UPDATE statements
    @:param column_list (list of str) - a list with the names of the MySQL database columns whose information is to be added to
    @:param table_name (str) - The name of the table where the Update statement is going to take effect
    @:param trigger_column_list (list of str) - The columns that are going to be used to identify the record to be updated (i.e., the WHERE column_name condition part of the statement). Each member of the provided list is going to be "AND"ed together
    in a single statement
    @:return sql_update (str) - The statement string to be executed with '%s' elements instead of the actual values in the statement (considered a more secure approach to run these statements from external applications such as this one).
    The actual values are to be replaced shortly before the execution of the statement, already in the database side of things
    @:raise utils.InputValidation Exception - if error occur during the validation of inputs
    @:raise Exception - for any other error types
    """
    utils.validate_input_type(column_list, list)
    for column_name in column_list:
        utils.validate_input_type(column_name, str)

    utils.validate_input_type(table_name, str)

    utils.validate_input_type(trigger_column_list, list)
    for trigger_column_name in trigger_column_list:
        utils.validate_input_type(trigger_column_name, str)

        if trigger_column_name not in column_list:
            error_msg = "The trigger column provided: {0} does not exist among the list of columns for {1}.{2}"\
                .format(str(trigger_column_name), str(user_config.access_info['mysql_database']['database']), str(table_name))
            raise utils.InputValidationException(message=error_msg)

    # If I'm still here (no Exceptions raised during the last command)
    sql_update = """UPDATE """ + str(table_name) + """ SET """
    for i in range(0, len(column_list)):
        sql_update += str(column_list[i]) + """ = %s, """

    # The last for loop add an extra ', ' at the end of the list as a consequence of it running all the way up to the last element on the list. So I need to drop these two extra characters before continuing the statement build
    sql_update = sql_update[0:-2] + """ WHERE """

    for i in range(0, len(trigger_column_list) - 1):
        sql_update += str(trigger_column_list[i]) + """ = %s AND """

    sql_update += str(trigger_column_list[-1]) + """ = %s;"""

    # Statement completed. Send it back to the user.
    return sql_update


def create_insert_sql_statement(column_list, table_name):
    """Method to automatize the building of simple SQL INSERT statements: INSERT INTO table_name (expanded, comma separated, column list names) VALUES (as many '%s' as column_list elements);
    @:param column_list (list of str) - A list with the names of the MySQL database columns
    @:param  table_name (str) - The name of the table where the INSERT statement is going to take effect
    @:return sql_insert (str) - The state,ent string to be executed with '%s' instead of actual values. These need to be replaced when executed in the database side (the python mysql connector deals with it quite nicely)
    @:raise utils.InputValidationException - If any errors occur during the input validation
    @:raise Exception - If any other general type errors occur"""

    utils.validate_input_type(column_list, list)
    for column_name in column_list:
        utils.validate_input_type(column_name, str)

    utils.validate_input_type(table_name, str)

    values_to_replace = []
    for i in range(0, len(column_list)):
        values_to_replace.append('%s')

    sql_insert = """INSERT INTO """ + str(table_name) + """ ("""
    sql_insert += """,""".join(column_list)
    sql_insert += """) VALUES ("""
    sql_insert += """, """.join(values_to_replace)
    sql_insert += """);"""

    # Done. Send it back for execution
    return sql_insert


def create_delete_sql_statement(table_name, trigger_column_list):
    """Method to automatize the building of SQL DELETE statements. These are generally simpler than UPDATE or INSERT ones
    @:database_name (str) - The name of the database in which this statement is going to be used. Needed for the validation of inputs
    @:param trigger_column_list (list of str) - The name of the columns that are going to be used in the DELETE statement (The WHERE trigger_column condition part goes). As with the UPDATE method, the DELETE statements produced through here are quite
    simple, i.e., the triggering condition is an equality and hence only one record at a time can be deleted via this method. Multiple trigger columns provided are going to be linked through 'AND' statements
    @:param table_name (str) - The name of the table where the DELETE statement is going to take effect
    @:return sql_delete (str) - The statement string to be executed with '%s' instead of values. These need to replaced afterwards in the parent function
    @:raise utils.InputValidationException - If the input arguments are invalid
    @:raise Exception - For any other error types"""

    utils.validate_input_type(table_name, str)
    utils.validate_input_type(trigger_column_list, list)

    # Check if the provided trigger column does exist in the database table
    column_list = get_table_columns(database_name=user_config.access_info['mysql_database']['database'], table_name=table_name)
    for trigger_column in trigger_column_list:
        if trigger_column not in column_list:
            raise utils.InputValidationException("The trigger column '{0}' provided doesn't exist in {1}.{2}'s columns"
                                                 .format(str(trigger_column), str(user_config.access_info['mysql_database']['database']), str(table_name)))

    # So far so good. Carry on with the statement build
    sql_delete = """DELETE FROM """ + str(table_name) + """ WHERE """
    for i in range(0, len(trigger_column_list) - 1):
        sql_delete += str(trigger_column_list[i]) + """ = %s AND """

    sql_delete += str(trigger_column_list[-1]) + """ = %s;"""

    return sql_delete


def convert_timestamp_tb_to_datetime(timestamp):
    """This method converts a specific timestamp from a ThingsBoard remote API request (which has one of the weirdest formats that I've seen around) and returns a datetime object that can be interpreted by the DATETIME data format of MySQL
    databases, i.e., YYYY-MM-DD hh:mm:ss, which also corresponds to the native datetime.datetime format from python
    @:param timestamp (int) - This is one of the trickiest elements that I've found so far. The ThingsBoard internal data is stored in a PostGres database. I'm assuming that is the one behind the data format returned by the remote API. Whatever
    it may be, it returns a 13 digit integer as the timestamp. A quick analysis suggests that this is a regular POSIX timestamp, i.e., the number of seconds from 1970-01-01 00:00:00 until whenever that data was inserted in the database.
    There are literally loads of different and straightforward ways to convert this value into a human-readable datetime. Yet none of them seemed to work with this particular value. In fact, none of the timestamps returned from the remote
    API was able to be converted into a datetime. And the reason is stupid as hell! It seems that, if you bother to count all seconds from 1970 until today, you get a number with 10 digits... and you have been getting that for quite some
    time given how long has to pass to add a new digit to this value. A bit more of investigation showed that, as well with regular datetime elements, POSIX timestamps also indicate the number of microseconds elapsed, but normally that is
    expressed as a 17 digit float in which the last 5 are the decimal part, i.e., the microseconds, but there's an obvious decimal point w«in those cases where the POSIX timestamp also has the number of microseconds. The only reasonable
    explanation (though somewhat weird in its own way) is that the value returned by the remote API contains 3 decimal digits and, for whatever reason behind it, the decimal point is omitted. It turns out that this is exactly what is going
    on! So I need to do extra flexing with this one... The method expects the 13 digit integer that comes straight from the remote API call and then itself does whatever needs to return a meaningful datetime
    @:return data_datetime (datetime.datetime) - A regular datetime object that can be sent directly to a MySQL database expecting a DATETIME field (YYYY-MM-DD hh:mm:ss)
    @:raise utils.InputValidationException - If there is something wrong with the validation of inputs
    @:raise Exception - For any other errors that may happen
    """
    times2date_log = ambi_logger.get_logger(__name__)

    try:
        utils.validate_input_type(timestamp, int)
    except utils.InputValidationException as ive:
        times2date_log.error(ive.message)
        raise ive

    # Given how weird are the datetime values returned by the ThingsBoard API, I'm going to extra anal with this one
    if len(str(timestamp)) != 13:
        error_msg = "Please provide the full value for the timestamp returned by the remote API (expecting a 13 digit int, got {0} digits.)".format(str(len(str(timestamp))))
        times2date_log.error(error_msg)
        raise Exception(error_msg)

    # All appears to be in good order so far. From here I could simply divide the timestamp value by 1000 to get it to 10 integer digits (+3 decimal) but I'm not particularly concerned about microseconds, really. So, might as well drop the
    # last 3 digits of the timestamp and call it a day (forcing a int cast after dividing the timestamp by 1000 effectively truncates the integer part of it, thus achieving the desired outcome)
    timestamp = int(timestamp/1000)

    # The rest is trivial
    return datetime.datetime.fromtimestamp(timestamp)


def convert_datetime_to_timestamp_tb(data_datetime):
    """This method is the literal inverse of the previous one: it receives a regular datetime object in the format YYYY-MM-DD hh:mm:ss.xxxx (I'm allowing microseconds in this one, if needed be) and returns the 13 digit timestamp that
    ThingsBoard's PostGres database expects
    @:param data_datetime (datetime.datetime) - A YYYY-MM-DD hh:mm:ss.xxxx representation of a date and a time, consistent with the datetime.datetime class
    @:return timestamp (int) - a 13 digit integer that its actually a 10 digit integer + 3 decimal digits with the decimal period omitted.
    @:raise utils.InputValidationException - For errors with the method's input arguments
    @:raise Exception - For all other errors
    """
    date2times_log = ambi_logger.get_logger(__name__)

    try:
        utils.validate_input_type(data_datetime, datetime.datetime)
    except utils.InputValidationException as ive:
        date2times_log.error(ive.message)
        raise ive

    # The conversion between datetime.datetime to timestamp is direct but this operation yields a number between 15 and 16 digits, depending on the time of the date that originated it. In any case, the integer part is always fixed (at
    # least for the next couple of decades or so) and it has 10 digits only. So the easiest approach is to multiply the resulting timestamp by 1000 and then re-cast it to integer to drop the remaining digits that I'm not interested,
    # regardless of exactly how many they were in the beginning
    return int(data_datetime.timestamp()*1000)


def run_sql_statement(cursor, sql_statement, data_tuple=()):
    """The way python runs SQL statements is a bit convoluted, with plenty of moving parts and things that can go wrong. Since I'm going to run plenty of these along this project, it is a good idea to abstract this operation as much as
    possible
    @:param cursor (mysql.connector.cursor.MySQLCursor) - A cursor object, obtained from an active database connection, that its used by python to run SQL statements as well as to process the results.
    @:param sql_statement (str) - THe SQL statement string to be executed, with its values not explicit but replaced by '%s' characters instead. This method takes care of this replacements.
    @:param data_tuple (tuple) - A tuple with as many elements as the ones to be replaced in the SQL string. The command that effectively runs the SQL statement takes two arguments: the original SQL string statement with '%s' elements
    instead of its values and a data tuple where those values are indicated in the expected order. The command then sends both elements across to be executed database side in a way that protects their content and integrity (supposedly, it
    wards against SQL injection attacks.
    @:raise utils.InputValidationException - If the input arguments fail their validations
    @:raise MySQLDatabaseException - For errors related to database operations
    @:raise Exception - For any other error that may occur.
    """
    run_sql_log = ambi_logger.get_logger(__name__)

    try:
        utils.validate_input_type(sql_statement, str)
        utils.validate_input_type(data_tuple, tuple)
    except utils.InputValidationException as ive:
        run_sql_log.error(ive.message)
        raise ive

    # Count the number of '%s' in the sql statement string and see if they match with the number of elements in the tuple
    if len(data_tuple) != sql_statement.count('%s'):
        error_msg = "Mismatch between the number of data tuple elements ({0}) and the number of replaceable '%s' in the sql statement string ({1})!".format(str(len(data_tuple)), str(sql_statement.count('%s')))
        run_sql_log.error(error_msg)
        raise MySQLDatabaseException(message=error_msg)

    # Done with the validations.
    try:
        cursor.execute(sql_statement, data_tuple)
    except Error as e:
        run_sql_log.error(e.msg)
        raise MySQLDatabaseException(message=e.msg, error_code=e.errno, sqlstate=e.sqlstate)

    return cursor


def validate_database_table_name(table_name):
    """This simple method receives a name of a table and validates it by executing a SQL statement in the default database to retrieve all of its tables and then checks if the table name in the input does match any of the returned values.
    @:param table_name (str) - The name of the database table whose existence is to be verified
    @:raise utils.InputValidationException - If the inputs fail initial validation
    @:raise MySQLDatabaseException - If any error occur while executing database bounded operations or if the table name was not found among the list of database tables retrieved
    @:return True (bool) - If table_name is among the database tables list"""

    validate_db_table_log = ambi_logger.get_logger(__name__)

    # Validate the input
    utils.validate_input_type(table_name, str)

    # Get the default database name
    database_name = user_config.mysql_db_access['database']
    # Create the database interface elements
    cnx = connect_db(database_name=database_name)
    select_cursor = cnx.cursor(buffered=True)

    # Prepare the SQL statement
    sql_select = """SHOW TABLES FROM """ + str(database_name) + """;"""

    # And execute it
    select_cursor = run_sql_statement(select_cursor, sql_select, ())

    # Check the data integrity first
    if not select_cursor.rowcount:
        error_msg = "The SQL statement '{0}' didn't return any results! Exiting...".format(str(select_cursor.statement))
        validate_db_table_log.error(error_msg)
        select_cursor.close()
        cnx.close()
        raise MySQLDatabaseException(message=error_msg)
    # If results were gotten
    else:
        # Grab the first one
        result = select_cursor.fetchone()

        # And run the next loop until all results were checked (result would be set to None once all the data retrieved from the database is exhausted)
        while result:
            # If a match is found
            if result == table_name:
                # Return the response immediately
                return True
            # Otherwise
            else:
                # Grab the next one and run another iteration of this
                result = select_cursor.fetchone()

        # If I got here it means none of the results matched the table_name provided. Nothing more to do than to inform that the table name is not valid
        raise MySQLDatabaseException(message="The table provided '{0}' is not among the current database tables!".format(str(table_name)))


def create_device_database_table(device_name, execute_script=True):
    """
    Use this method to generate and execute a .sql script to create a table dedicated to store the data produced by the device identified by device_name. This is necessary since each device has its own set of timeseries keys. Creating a table in a
    relational database with this kind of constraints is almost impossible. But what I can do is some clever programming to automate this script building and even executing, based only on the typical return of the telemetry service for this device.
    @:param device_name (str) - Name of the device, as it is set in the Thingsboard interface, to be used as based to built the respective database table.
    @:param execute_script (bool) - Set this flag to True to execute the database table creation script if it gets generated successfully. Set it to false to generate just the sql script
    @:raise utils.InputValidationException - If the the input fails initial validation
    @:raise mysql_utils.MySQLDatabaseException - If any problems occur when accessing/configuring the database.
    @:return create_table_name (str) - If a table was created using the provided device_name, None otherwise
    """
    log = ambi_logger.get_logger(__name__)

    # Validate inputs first
    utils.validate_input_type(device_name, str)
    utils.validate_input_type(execute_script, bool)

    table_to_create = get_official_device_table_name(device_name=device_name)
    database_name = user_config.access_info['mysql_database']['database']

    # Before moving forward, check the database to see if a table with the expected name (<device_name>_data) exists already
    if validate_table_name(table_to_create):
        log.warning("There's a table named '{0}' already in database {1}. Nothing more to do..".format(str(table_to_create), str(database_name)))
        # Send back the name of the table that was found by the validation method so that it can be used by the parent method
        return table_to_create

    # All seems alright. Proceed by running the getLatestTimeseries method to retrieve all data that the device in question can produce, as well as the most recent timestamps associated to it
    device_data = tb_telemetry_controller.getLatestTimeseries(device_name=device_name)

    # Check if a valid result was obtained first
    if device_data is None:
        error_msg = "Could not retrieve any telemetry data for device '{0}'".format(str(device_name))
        log.error(error_msg)
        raise utils.InputValidationException(message=error_msg)

    # It seems that I can proceed with the .sql file build then.from
    sql_script_path = os.path.join(os.getcwd(), 'mysql_database', 'thingsboard_device_tables', 'create_' + table_to_create + "_table.sql")
    # Open the file defined by the previous path with a 'w' (write flag)
    sql_script = open(sql_script_path, 'w')

    # Lets start doing stuff then
    script_content = ["CREATE TABLE IF NOT EXISTS {0}.{1}\n".format(str(database_name), str(table_to_create)), "(\n", "\ttimestamp\t\t\tDATETIME DEFAULT NULL NULL,\n"]

    # Create a head timestamp column that is going to be common to all records

    # And now add a column to each of the keys in the current device data dictionary
    for column_name in list(device_data.keys()):
        line = "\t" + column_name
        # Calculate the number of tabs to add after the column name to ensure that the rest of the fields remain aligned. Each tab is 8 characters and I want 5 tabs (40 characters worth) of space between the start of the column name and its type
        tab_number = int((40 - len(column_name))/8)
        for i in range(0, tab_number):
            line += '\t'
        # Complete the rest of this line
        line += "DOUBLE DEFAULT NULL NULL,\n"
        script_content.append(line)

    # Finish the script by establishing the timestamp column as the primary key
    script_content.append("\tCONSTRAINT " + table_to_create + "_pk UNIQUE (timestamp)\n")
    script_content.append(")\n")
    script_content.append("COMMENT 'This script was automatically created using mysql_database.python_database_modules.mysql_utils.device_database_table_script_generator method';\n")
    script_content.append("COMMIT;")

    # All lines were created. Write them into the file and close it
    sql_script.writelines(script_content)
    sql_script.flush()
    sql_script.close()

    log.info("Create {0} SQL script successfully!".format(str(sql_script_path)))

    # Now that the script is ready, take the opportunity that I still have its path to execute it using the mysql.exe executable if the respective input flag was set. If the environment variables are well set, there should be no difference between
    # running the next statement in either a Microsoft (Windows) or Linux Operating Systems: The syntax is identical for both OS's
    if execute_script:
        os.system('mysql.exe --verbose --user="{0}" --database="{1}" --password={2} < "{3}"'.format(
            str(user_config.access_info['mysql_database']['username']),
            str(user_config.access_info['mysql_database']['database']),
            str(user_config.access_info['mysql_database']['password']),
            str(sql_script_path)))

        # Done. Inform the user of the success of this operation and return the name of the database table just created
        log.info("Created the table {0} in {1} database successfully!".format(str(table_to_create), str(database_name)))

    return table_to_create


def get_official_device_table_name(device_name):
    """
    This simple method receives the name of a device and returns what should be the name of the database table that can hold its data. This conversion needs to be uniform, following the same kind of rules for all device names (replacing spaces,
    dots and slashes by underscores and appending '_data' to the result) so that other methods can confirm in advance if a table for a given device already exists or not
    @:param device_name (str) - The name of the device to model the table name after
    @:return table_name_to_create (str) - The result of the transformation of the provided device_name into the expected database table name.
    @:raise utils.InputValidationException - If the input fails initial validation
    """
    utils.validate_input_type(device_name, str)

    # Return the name of the device appended with '_data' and all its dashes ('-'), spaces and points ('.') replaced by underscores ('_')
    return device_name.replace(' ', '_').replace('.', '_').replace('-', '_') + "_data"


def validate_table_name(table_name):
    """
    This method receives the name of a database table and checks the database for its existence. That's it.
    @:param table_name (str) - The name of the table whose existence is to be verified in the database
    @:return exists (bool) - True if the table is already created in the database, False otherwise
    @:raise utils.InputValidationException - If the input fails initial validation
    @:raise MySQLDatabaseException - If errors occur during the database accesses
    """
    log = ambi_logger.get_logger(__name__)
    utils.validate_input_type(table_name, str)

    # Need to access the database. Create the usual objects
    database_name = user_config.access_info['mysql_database']['database']
    cnx = connect_db(database_name=database_name)
    select_cursor = cnx.cursor(buffered=True)

    sql_select = """SHOW TABLES FROM """ + database_name + """;"""

    select_cursor = run_sql_statement(cursor=select_cursor, sql_statement=sql_select, data_tuple=())

    if select_cursor.rowcount is 0:
        log.warning("The current database ({0}) has no tables configured yet!".format(str(database_name)))
        select_cursor.close()
        cnx.close()
        return False

    else:
        results = select_cursor.fetchall()

        for i in range(0, len(results)):
            if table_name == results[i][0]:
                select_cursor.close()
                cnx.close()
                return True

        # If the code reached this point, then I've verified all existing tables currently in the database and didn't find any matches
        select_cursor.close()
        cnx.close()
        return False
