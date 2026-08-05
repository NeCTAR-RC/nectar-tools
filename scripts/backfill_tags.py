import argparse
import datetime
import influxdb
import logging

# Configuration
INFLUXDB_HOST = 'localhost'
INFLUXDB_PORT = 8086

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_time_to_tags(time_str):
    dt = datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%SZ")
    return {
        'week_of_the_year': int(dt.strftime("%U")),
        'day_of_the_year': int(dt.strftime("%-j")),
        'month': int(dt.strftime("%-m")),
        'year': int(dt.strftime("%Y"))
    }

def backfill_tags(start, end, username, password, database, measurement, batch_size, execute, limit):
    # Connect to InfluxDB
    client_args = {
        'host': INFLUXDB_HOST,
        'port': INFLUXDB_PORT,
        'database': database
    }
    if username and password:
        client_args['username'] = username
        client_args['password'] = password

    client = influxdb.InfluxDBClient(**client_args)
    # Query existing data
    limit_clause = f'LIMIT {limit}' if limit else ''
    query = f'SELECT * FROM {measurement} WHERE time >= \'{start}\' AND time < \'{end}\' AND year = \'\' {limit_clause}'
    results = client.query(query)

    # Prepare new data with additional tags
    new_points = []
    count = 0
    all_points = list(results.get_points())
    for point in all_points:
        count += 1
        new_tags = {
            'id': point['id'],
            'user_id': point['user_id'],
            'project_id': point['project_id'],
            'type': point['type'],
            **parse_time_to_tags(point['time'])
        }

        new_fields = {k: v for k, v in point.items() if k not in new_tags and k != 'time'}
        new_fields['groupby'] = 'id|project_id|user_id|week_of_the_year|day_of_the_year|month|year'

        new_points.append({
            "measurement": measurement,
            "tags": new_tags,
            "fields": new_fields,
            "time": point['time']
        })

        if len(new_points) >= batch_size:

            if execute:
                logger.info("Writing points to InfluxDB...")
                success = client.write_points(new_points)
                if not success:
                    raise Exception("Failed to write points to InfluxDB")
            else:
                logger.info("Dry run mode. The following points would be written:")
                for point in new_points:
                    logger.info(point)
            new_points = []

    if new_points:
        if execute:
            logger.info("Writing points to InfluxDB...")
            success = client.write_points(new_points)
            if not success:
                raise Exception("Failed to write points to InfluxDB")
        else:
            logger.info("Dry run mode. The following points would be written:")
            for point in new_points:
                logger.info(point)

    logger.info("Backfill complete with %s points.", len(all_points))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Backfill tag keys into InfluxDB measurements.')
    parser.add_argument('--start', required=True, help='Start time in ISO8601 format')
    parser.add_argument('--end', required=True, help='End time in ISO8601 format')
    parser.add_argument('--username', help='InfluxDB username')
    parser.add_argument('--password', help='InfluxDB password')
    parser.add_argument('--database', default='cloudkitty', help='InfluxDB database name')
    parser.add_argument('--measurement', default='dataframes', help='InfluxDB measurement name')
    parser.add_argument('--batch-size', type=int, default=5000, help='Batch size for writing points to InfluxDB')
    parser.add_argument('--execute', action='store_true', help='Run script in execute mode (default is dry run)')
    parser.add_argument('--limit', type=int, help='Limit the max number of datapoints to be updated')
    args = parser.parse_args()

    backfill_tags(args.start, args.end, args.username, args.password, args.database, args.measurement, args.batch_size, args.execute, args.limit)
