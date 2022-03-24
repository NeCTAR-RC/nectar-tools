import datetime

from nectar_tools import auth


DATE_FORMAT = '%Y-%m-%d'


def get_allocation_usage(session, allocation):
    client = auth.get_cloudkitty_client(session)
    summary = client.summary.get_summary(
        begin=str(allocation.start_date), end=str(allocation.end_date),
        filters={'type': 'instance', 'project_id': allocation.project_id},
        response_format='object')

    results = summary.get('results')
    if results:
        return results[0].get('rate')
    return 0


def allocation_over_budget(session, allocation):

    budget = allocation.get_allocated_cloudkitty_quota().get('budget')
    if not budget or budget == 0:
        return False
    usage = get_allocation_usage(session, allocation)
    allocation_start = datetime.datetime.strptime(
        allocation.start_date, DATE_FORMAT)
    allocation_end = datetime.datetime.strptime(
        allocation.end_date, DATE_FORMAT)

    today = datetime.datetime.today()
    allocation_total_days = (allocation_end - allocation_start).days
    days_used = (today - allocation_start).days
    return usage / budget > days_used / allocation_total_days
