import subsidy_service as service

# Globals
CONF = service.utils.get_config()
CLIENT = service.mongo.get_client(CONF)
DB = CLIENT.subsidy


# CRUD functionality
def create(subsidy: dict):
    """
    Create a new subsidy for a citizen. If the citizen is not yet in the
    database, they are added. A new bank account is created, the amount of the
    subsidy is transferred from the master to the subsidy account, and a
    connect invite is sent to the recipient.

    :param subsidy: Subsidy to create
    :return: The created subsidy
    """
    recip = service.utils.drop_nones(subsidy['recipient'])

    recip_full = service.mongo.find(recip, DB.citizens)  # TODO: Remove

    if recip_full:
        recip = recip_full.copy()
        recip.pop('subsidies')
        subsidy['recipient'] = recip
    else:
        #TODO: Determine if this is desirable
        service.citizens.create(subsidy['recipient'])

    # TODO: Move to actions/approve
    new_acct = service.bunq.create_account()
    new_acct['bunq_id'] = new_acct.pop('id')

    update_accounts()  # TODO: Get rid of this once we have master accounts
    master = service.mongo.find(service.utils.drop_nones(subsidy['master']),
                                DB.accounts)

    pmt = service.bunq.make_payment_to_acct_id(master['bunq_id'],
                                               new_acct['bunq_id'],
                                               subsidy['amount'])

    new_acct['balance'] = -float(pmt['amount'])

    new_share = service.bunq.create_share(new_acct['bunq_id'],
                                          recip['phone_number'])

    subsidy['account'] = new_acct
    subsidy['master'] = master


    if not recip_full['subsidies']:
        recip_full['subsidies'] = [subsidy]
    else:
        recip_full['subsidies'].append(subsidy)

    service.mongo.update_by_id(recip_full['id'], recip_full, DB.citizens)

    output = service.mongo.add_and_copy_id(subsidy, DB.subsidies)

    return service.utils.drop_nones(output)


def read(id):
    """
    Get a subsidy by ID

    :param id: the subsidy's ID
    :return: dict
    """
    return service.mongo.get_by_id(id, DB.subsidies)


def read_all():
    """
    Get all available subsidies

    :return: dict
    """
    return service.mongo.get_collection(DB.subsidies)


def update(id, subsidy: dict):
    """
    Update a subsidy's information.

    :param id: the subsidy's id
    :param subsidy: the fields to update. Nones will be ignored.
    :return: the updated subsidy
    """
    document = service.utils.drop_nones(subsidy)
    obj = service.mongo.update_by_id(id, document, DB.subsidies)
    return obj


def replace(id, subsidy: dict):
    """
    Replace a subsidy in the database with the provided subsidy, preserving ID.

    :param id: the subsidy's id
    :param subsidy: the new details
    :return: the new subsidy's details
    """
    document = subsidy
    document['id'] = str(id)
    obj = service.mongo.replace_by_id(id, document, DB.subsidies)
    return obj


def delete(id):
    """
    Remove a subsidy, revoking any related shares and closing related account.

    :param id: the id of the subsidy to delete.
    :return: None
    """
    subsidy = service.mongo.get_by_id(id, DB.subsidies)

    acct = service.bunq.read_account(subsidy['account']['bunq_id'])
    balance = acct['balance']

    if float(balance) > 0:
        pmt = service.bunq.make_payment_to_acct_id(
            subsidy['account']['bunq_id'],
            subsidy['master']['bunq_id'],
            balance
        )

    service.bunq.close_account(subsidy['account']['bunq_id'])
    service.mongo.delete_by_id(id, DB.subsidies)

    return None


# utilities
def update_accounts():
    accts = service.bunq.list_accounts(include_closed=True)
    for acct in accts:
        acct_db = acct.copy()
        acct_db['bunq_id'] = acct_db.pop('id')
        service.mongo.upsert(acct_db, DB.accounts, ['iban'])

    accts_db = service.mongo.get_collection(DB.accounts)

    return accts_db
