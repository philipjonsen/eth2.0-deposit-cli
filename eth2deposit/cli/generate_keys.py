import os
import click
from typing import (
    Any,
    Callable,
)

from eth_typing import HexAddress
from eth_utils import is_hex_address, to_normalized_address

from eth2deposit.credentials import (
    CredentialList,
)
from eth2deposit.exceptions import ValidationError
from eth2deposit.utils.validation import (
    verify_deposit_data_json,
    validate_password_strength,
)
from eth2deposit.utils.constants import (
    MAX_DEPOSIT_AMOUNT,
    DEFAULT_VALIDATOR_KEYS_FOLDER_NAME,
)
from eth2deposit.utils.ascii_art import RHINO_0
from eth2deposit.utils.click import jit_option
from eth2deposit.utils.intl import load_text
from eth2deposit.settings import (
    ALL_CHAINS,
    MAINNET,
    get_chain_setting,
)


def get_password(text: str) -> str:
    return click.prompt(text, hide_input=True, show_default=False, type=str)


def validate_password(cts: click.Context, param: Any, password: str) -> str:
    is_valid_password = False

    # The given password has passed confirmation
    try:
        validate_password_strength(password)
    except ValidationError as e:
        click.echo(e)
    else:
        is_valid_password = True

    while not is_valid_password:
        password = get_password(load_text(['msg_password_prompt']))
        try:
            validate_password_strength(password)
        except ValidationError as e:
            click.echo(e)
        else:
            # Confirm password
            password_confirmation = get_password(load_text(['msg_password_confirm']))
            if password == password_confirmation:
                is_valid_password = True
            else:
                click.echo(load_text(['err_password_mismatch']))

    return password


def validate_eth1_withdrawal_address(cts: click.Context, param: Any, address: str) -> HexAddress:
    if address is None:
        return None
    if not is_hex_address(address):
        raise ValueError("The given Eth1 address is not in hexadecimal encoded form.")

    normalized_address = to_normalized_address(address)
    click.echo(f'\n**[Warning] you are setting Eth1 address {normalized_address} as your withdrawal address. '
               'Please ensure that you have control over this address.**\n')
    return normalized_address


def generate_keys_arguments_decorator(function: Callable[..., Any]) -> Callable[..., Any]:
    '''
    This is a decorator that, when applied to a parent-command, implements the
    to obtain the necessary arguments for the generate_keys() subcommand.
    '''
    decorators = [
        jit_option(
            help=lambda: load_text(['num_validators', 'help'], func='generate_keys_arguments_decorator'),
            param_decls="--num_validators",
            prompt=lambda: load_text(['num_validators', 'prompt'], func='generate_keys_arguments_decorator'),
            required=True,
            type=click.IntRange(0, 2**32 - 1),
        ),
        jit_option(
            default=os.getcwd(),
            help=lambda: load_text(['folder', 'help'], func='generate_keys_arguments_decorator'),
            param_decls='--folder',
            type=click.Path(exists=True, file_okay=False, dir_okay=True),
        ),
        jit_option(
            default=MAINNET,
            help=lambda: load_text(['chain', 'help'], func='generate_keys_arguments_decorator'),
            param_decls='--chain',
            prompt=lambda: load_text(['chain', 'prompt'], func='generate_keys_arguments_decorator'),
            type=click.Choice(ALL_CHAINS.keys(), case_sensitive=False),
        ),
        jit_option(
            callback=validate_password,
            confirmation_prompt=True,
            help=lambda: load_text(['keystore_password', 'help'], func='generate_keys_arguments_decorator'),
            hide_input=True,
            param_decls='--keystore_password',
            prompt=lambda: load_text(['keystore_password', 'prompt'], func='generate_keys_arguments_decorator'),
        ),
        click.option(
            '--eth1_withdrawal_address',
            default=None,
            callback=validate_eth1_withdrawal_address,
            help=('If this field is set and valid, the given Eth1 address will be used to create the '
                  'withdrawal credentials. Otherwise, it will generate withdrawal credentials with the '
                  'mnemonic-derived withdrawal public key.'),
        ),
    ]
    for decorator in reversed(decorators):
        function = decorator(function)
    return function


@click.command()
@click.pass_context
def generate_keys(ctx: click.Context, validator_start_index: int,
                  num_validators: int, folder: str, chain: str, keystore_password: str,
                  eth1_withdrawal_address: HexAddress, **kwargs: Any) -> None:
    mnemonic = ctx.obj['mnemonic']
    mnemonic_password = ctx.obj['mnemonic_password']
    amounts = [MAX_DEPOSIT_AMOUNT] * num_validators
    folder = os.path.join(folder, DEFAULT_VALIDATOR_KEYS_FOLDER_NAME)
    chain_setting = get_chain_setting(chain)
    if not os.path.exists(folder):
        os.mkdir(folder)
    click.clear()
    click.echo(RHINO_0)
    click.echo(load_text(['msg_key_creation']))
    credentials = CredentialList.from_mnemonic(
        mnemonic=mnemonic,
        mnemonic_password=mnemonic_password,
        num_keys=num_validators,
        amounts=amounts,
        chain_setting=chain_setting,
        start_index=validator_start_index,
        hex_eth1_withdrawal_address=eth1_withdrawal_address,
    )
    keystore_filefolders = credentials.export_keystores(password=keystore_password, folder=folder)
    deposits_file = credentials.export_deposit_data_json(folder=folder)
    if not credentials.verify_keystores(keystore_filefolders=keystore_filefolders, password=keystore_password):
        raise ValidationError(load_text(['err_verify_keystores']))
    if not verify_deposit_data_json(deposits_file, credentials.credentials):
        raise ValidationError(load_text(['err_verify_deposit']))
    click.echo(load_text(['msg_creation_success']) + folder)
    click.pause(load_text(['msg_pause']))
