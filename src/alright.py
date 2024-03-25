from typing import Literal

import beaker
import beaker.lib.storage.box_mapping as box_mapping
import pyteal as pt

from smart_contracts.helpers.deployment_standard import (
    deploy_time_immutability_control,
    deploy_time_permanence_control,
)

# Math for determining min balance
BoxFlatMBR = 2500
BoxByteMBR = 400
DealListKeyLength = 32
DealListBoxLength = 1023
DealListCost = BoxFlatMBR + (BoxByteMBR * (DealListBoxLength + DealListKeyLength))
DealDetailsKeyLength = 33
DealDetailsBoxLength = 1024
DealDetailsCost = BoxFlatMBR + (
    BoxByteMBR * (DealDetailsBoxLength + DealDetailsKeyLength)
)
DealDataKeyLength = 64
# DealDataBoxSize = 32768 + 64
# First deal box setup requires MBR 424500 + 424500 + 425300 = 1274300


class AlrightState:
    owner = beaker.GlobalStateValue(
        stack_type=pt.TealType.bytes,
        default=pt.Global.creator_address(),
        descr="Account that controls the app",
    )
    status = beaker.GlobalStateValue(
        stack_type=pt.TealType.bytes,
        default=pt.Bytes("inactive"),
        descr="Application status",
    )
    total_deals = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64, default=pt.Int(0), descr="Total deals"
    )
    active_deals = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64, default=pt.Int(0), descr="Active deals"
    )
    completed_deals = beaker.GlobalStateValue(
        stack_type=pt.TealType.uint64, default=pt.Int(0), descr="Completed deals"
    )

    # Reserving up to max 64 global state slots, 32 bytes/uints
    reserved_global_bytes_value = beaker.ReservedGlobalStateValue(
        stack_type=pt.TealType.bytes,
        max_keys=30,
        descr="Reserved global state bytes value with 30 possible keys",
    )
    reserved_global_uint_value = beaker.ReservedGlobalStateValue(
        stack_type=pt.TealType.uint64,
        max_keys=29,
        descr="Reserved global state uint value with 29 possible keys",
    )


app = (
    beaker.Application(
        name="AlrightApp",
        state=AlrightState(),
        descr="Peer-to-peer escrow agreements powered by Algorand",
        build_options=beaker.BuildOptions(
            avm_version=8,
        ),
    )
    .apply(deploy_time_immutability_control)
    .apply(deploy_time_permanence_control)
    .apply(beaker.unconditional_create_approval, initialize_global_state=True)
)

deal_key = pt.ScratchVar(pt.TealType.bytes)
deal_value = pt.ScratchVar(pt.TealType.bytes)
sender_abi = pt.abi.make(pt.abi.Address)
their_address_abi = pt.abi.make(pt.abi.Address)

DealKey = pt.abi.StaticBytes[Literal[33]]


class DealValue(pt.abi.NamedTuple):
    first_acc_status: pt.abi.Field[pt.abi.Byte]  #                 1 byte
    second_acc_status: pt.abi.Field[pt.abi.Byte]  #                1 byte
    first_acc_address: pt.abi.Field[pt.abi.Address]  #            32 bytes
    first_acc_dep_amount: pt.abi.Field[pt.abi.Uint64]  #           8 bytes
    first_acc_dep_asset: pt.abi.Field[pt.abi.Uint64]  #            8 bytes
    first_acc_col_amount: pt.abi.Field[pt.abi.Uint64]  #           8 bytes
    first_acc_col_asset: pt.abi.Field[pt.abi.Uint64]  #            8 bytes
    second_acc_address: pt.abi.Field[pt.abi.Address]  #           32 bytes
    second_acc_dep_amount: pt.abi.Field[pt.abi.Uint64]  #          8 bytes
    second_acc_dep_asset: pt.abi.Field[pt.abi.Uint64]  #           8 bytes
    second_acc_col_amount: pt.abi.Field[pt.abi.Uint64]  #          8 bytes
    second_acc_col_asset: pt.abi.Field[pt.abi.Uint64]  #           8 bytes
    first_acc_forward_amount: pt.abi.Field[pt.abi.Uint64]  #       8 bytes
    second_acc_forward_amount: pt.abi.Field[pt.abi.Uint64]  #      8 bytes
    first_acc_data: pt.abi.Field[pt.abi.Byte]  #                   1 byte
    second_acc_data: pt.abi.Field[pt.abi.Byte]  #                  1 byte
    deal_note: pt.abi.Field[
        pt.abi.String
    ]  # Dynamic up to 874 bytes (string <=872 for 1024 box size)


all_deal_boxes = box_mapping.BoxMapping(DealKey, DealValue)

dv = deal_value.load()

# fmt:off
first_acc_status_ex = pt.Extract(dv,              pt.Int(  0), pt.Int(  1))
second_acc_status_ex = pt.Extract(dv,             pt.Int(  1), pt.Int(  1))
first_acc_address_ex = pt.Extract(dv,             pt.Int(  2), pt.Int( 32))
first_acc_dep_amount_ex = pt.Extract(dv,          pt.Int( 34), pt.Int(  8))
first_acc_dep_asset_ex = pt.Extract(dv,           pt.Int( 42), pt.Int(  8))
first_acc_col_amount_ex = pt.Extract(dv,          pt.Int( 50), pt.Int(  8))
first_acc_col_asset_ex = pt.Extract(dv,           pt.Int( 58), pt.Int(  8))
second_acc_address_ex = pt.Extract(dv,            pt.Int( 66), pt.Int( 32))
second_acc_dep_amount_ex = pt.Extract(dv,         pt.Int( 98), pt.Int(  8))
second_acc_dep_asset_ex = pt.Extract(dv,          pt.Int(106), pt.Int(  8))
second_acc_col_amount_ex = pt.Extract(dv,         pt.Int(114), pt.Int(  8))
second_acc_col_asset_ex = pt.Extract(dv,          pt.Int(122), pt.Int(  8))
first_acc_forward_amount_ex = pt.Extract(dv,      pt.Int(130), pt.Int(  8))
second_acc_forward_amount_ex = pt.Extract(dv,     pt.Int(138), pt.Int(  8))
first_acc_data = pt.Extract(dv,                   pt.Int(146), pt.Int(  1))
second_acc_data = pt.Extract(dv,                  pt.Int(147), pt.Int(  1))
# fmt:on


# A hack to include the DealValue named tuple for creating a codec
@app.external(authorize=beaker.Authorize.only(app.state.owner))
def deal_value_method(deal_value: DealValue) -> pt.Expr:
    return pt.Reject()


@app.external
def hello(name: pt.abi.String, *, output: pt.abi.String) -> pt.Expr:
    return output.set(
        pt.Concat(pt.Bytes("Hello, "), name.get(), pt.Bytes(". You alright?"))
    )


@app.external(authorize=beaker.Authorize.only(app.state.owner))
def change_status(new_status: pt.abi.String, *, output: pt.abi.String) -> pt.Expr:
    return pt.Seq(
        app.state.status.set(new_status.get()),
        output.set(app.state.status.get()),
    )


@app.external(authorize=beaker.Authorize.only(app.state.owner))
def change_owner(new_owner: pt.abi.Address, *, output: pt.abi.Address) -> pt.Expr:
    return pt.Seq(
        pt.Assert(
            pt.Balance(new_owner.get()) > pt.Int(0), comment="New owner balance > 0"
        ),
        app.state.owner.set(new_owner.get()),
        output.set(app.state.owner.get()),
    )


@app.external(authorize=beaker.Authorize.only(app.state.owner))
def send_note(
    receiver: pt.abi.Address, note: pt.abi.String, *, output: pt.abi.String
) -> pt.Expr:
    return pt.Seq(
        pt.InnerTxnBuilder.Execute(
            {
                pt.TxnField.type_enum: pt.TxnType.Payment,
                pt.TxnField.amount: pt.Int(0),
                pt.TxnField.receiver: receiver.get(),
                pt.TxnField.note: note.get(),
                pt.TxnField.fee: pt.Int(0),
            }
        ),
        output.set(note.get()),
    )


@app.external(authorize=beaker.Authorize.only(app.state.owner))
def verify_nfd(
    nfd_name: pt.abi.String, nfd_app_id: pt.abi.Uint64, *, output: pt.abi.String
) -> pt.Expr:
    return pt.Seq(
        pt.InnerTxnBuilder.Execute(
            {
                pt.TxnField.type_enum: pt.TxnType.ApplicationCall,
                pt.TxnField.fee: pt.Int(0),
                pt.TxnField.application_id: nfd_app_id.get(),
                pt.TxnField.application_args: [
                    pt.Bytes("verify_nfd_addr"),
                    nfd_name.get(),
                    pt.Itob(nfd_app_id.get()),
                    pt.Global.current_application_address(),
                ],
            }
        ),
        output.set(pt.InnerTxn.last_log()),
    )


@app.external(authorize=beaker.Authorize.only(app.state.owner))
def opt_in_to_asa(
    asset: pt.abi.Asset, payment: pt.abi.PaymentTransaction, *, output: pt.abi.String
) -> pt.Expr:
    return pt.Seq(
        pt.Assert(
            payment.get().amount() >= pt.Int(100_000), comment="MBR payment >= 0.1A"
        ),
        pt.Assert(
            payment.get().receiver() == pt.Global.current_application_address(),
            comment="MBR payment to this app",
        ),
        pt.InnerTxnBuilder.Execute(
            {
                pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
                pt.TxnField.xfer_asset: asset.asset_id(),
                pt.TxnField.asset_amount: pt.Int(0),
                pt.TxnField.asset_receiver: pt.Global.current_application_address(),
                pt.TxnField.fee: pt.Int(0),
            }
        ),
        output.set(pt.InnerTxn.tx_id()),
    )


@pt.Subroutine(pt.TealType.none)
def send_algo_or_asa(
    asset_id: pt.Expr,
    amount: pt.Expr,
    account: pt.Expr,
    note: pt.Expr,
) -> pt.Expr:
    return pt.Seq(
        pt.If(amount != pt.Int(0)).Then(
            pt.If(asset_id == pt.Int(0))
            .Then(
                pt.InnerTxnBuilder.Execute(
                    {
                        pt.TxnField.type_enum: pt.TxnType.Payment,
                        pt.TxnField.amount: amount,
                        pt.TxnField.receiver: account,
                        pt.TxnField.fee: pt.Int(0),
                        pt.TxnField.note: note,
                    }
                ),
            )
            .Else(
                pt.InnerTxnBuilder.Execute(
                    {
                        pt.TxnField.type_enum: pt.TxnType.AssetTransfer,
                        pt.TxnField.xfer_asset: asset_id,
                        pt.TxnField.asset_amount: amount,
                        pt.TxnField.asset_receiver: account,
                        pt.TxnField.fee: pt.Int(0),
                        pt.TxnField.note: note,
                    }
                ),
            ),
        )
    )


@pt.Subroutine(pt.TealType.bytes)
def create_deal_key(their_address: pt.Expr, deal_note: pt.Expr) -> pt.Expr:
    return pt.Seq(
        pt.Assert(
            pt.Len(their_address) == pt.Int(32), comment="their_address length=32"
        ),
        pt.Assert(
            pt.BytesNeq(pt.Txn.sender(), their_address),
            comment="Accounts different",
        ),
        pt.If(pt.BytesGt(pt.Txn.sender(), their_address))
        .Then(
            pt.Concat(
                pt.Bytes("D"),
                pt.Sha256(pt.Concat(pt.Txn.sender(), their_address, deal_note)),
            )
        )
        .Else(
            pt.Concat(
                pt.Bytes("D"),
                pt.Sha256(pt.Concat(their_address, pt.Txn.sender(), deal_note)),
            )
        ),
    )


@pt.Subroutine(pt.TealType.none)
def record_deal_key(
    address: pt.Expr,
    deal_key: pt.Expr,
    key_index: pt.Expr,
    registration_cost_accumulator: pt.ScratchVar,
) -> pt.Expr:
    # Deal keys box is 1023 bytes with 31x 33-byte slots
    return pt.Seq(
        box_contents := pt.BoxGet(address),
        pt.If(box_contents.hasValue())
        .Then(
            pt.Assert(
                pt.Extract(
                    box_contents.value(),
                    key_index * pt.Int(DealDetailsKeyLength),
                    pt.Int(DealDetailsKeyLength),
                )
                == pt.BytesZero(pt.Int(DealDetailsKeyLength)),
                comment="deal_key[index] is zero bytes",
            ),
            pt.BoxReplace(address, key_index * pt.Int(DealDetailsKeyLength), deal_key),
        )
        .Else(
            pt.Pop(pt.BoxCreate(address, pt.Int(DealListBoxLength))),
            registration_cost_accumulator.store(
                registration_cost_accumulator.load() + pt.Int(DealListCost)
            ),
            pt.BoxReplace(address, pt.Int(0), deal_key),
        ),
    )


@pt.Subroutine(pt.TealType.uint64)
def confirm_deal_key_at_index(
    address: pt.Expr, deal_key: pt.Expr, key_index: pt.Expr
) -> pt.Expr:
    # Deal keys box is 1023 bytes with 31x 33-byte slots
    return pt.Seq(
        box_contents := pt.BoxGet(address),
        pt.If(box_contents.hasValue()).Then(
            pt.If(box_contents.value() == pt.BytesZero(pt.Int(DealListBoxLength))).Then(
                pt.Return(pt.Int(0))
            ),
            pt.If(
                pt.Extract(
                    box_contents.value(),
                    key_index * pt.Int(DealDetailsKeyLength),
                    pt.Int(DealDetailsKeyLength),
                )
                == deal_key
            ).Then(
                pt.Return(pt.Int(1)),
            ),
        ),
        pt.Return(pt.Int(0)),
    )


@pt.Subroutine(pt.TealType.none)
def check_deal_keys(
    deal_key: pt.Expr,
    key_index: pt.Expr,
    their_address: pt.Expr,
    their_key_index: pt.Expr,
) -> pt.Expr:
    return pt.Seq(
        # Check that the app is active
        pt.Assert(app.state.status == pt.Bytes("active"), comment="App is active"),
        pt.Assert(pt.Txn.sender() != their_address, comment="Addresses not equal"),
        pt.Assert(
            pt.Len(deal_key) == pt.Int(DealDetailsKeyLength), comment="deal_key len=33"
        ),
        # Confirm that this deal ID is recorded in both accounts' deal lists
        pt.Assert(
            confirm_deal_key_at_index(pt.Txn.sender(), deal_key, key_index)
            == pt.Int(1),
            comment="Deal key in sender list",
        ),
        pt.Assert(
            confirm_deal_key_at_index(their_address, deal_key, their_key_index)
            == pt.Int(1),
            comment="Deal key in their list",
        ),
    )


@pt.Subroutine(pt.TealType.none)
def erase_deal_key_at_index(address: pt.Expr, key_index: pt.Expr) -> pt.Expr:
    # Deal keys box is 1023 bytes with 31x 33-byte slots
    return pt.Seq(
        box_contents := pt.BoxGet(address),
        pt.If(box_contents.hasValue()).Then(
            pt.BoxReplace(
                address,
                key_index * pt.Int(DealDetailsKeyLength),
                pt.BytesZero(pt.Int(DealDetailsKeyLength)),
            ),
        ),
    )


@pt.Subroutine(pt.TealType.none)
def send_disbursements() -> pt.Expr:
    return pt.Seq(
        # Send first account deposit
        # If first_acc_deposit amount = forward amount, send to second account
        pt.If(first_acc_dep_amount_ex == first_acc_forward_amount_ex).Then(
            send_algo_or_asa(
                pt.Btoi(first_acc_dep_asset_ex),
                pt.Btoi(first_acc_dep_amount_ex),
                second_acc_address_ex,
                pt.Bytes("Payment forward"),
            )
        )
        # Elseif forward amount = 0, return to first account
        .ElseIf(pt.Btoi(first_acc_forward_amount_ex) == pt.Int(0)).Then(
            send_algo_or_asa(
                pt.Btoi(first_acc_dep_asset_ex),
                pt.Btoi(first_acc_dep_amount_ex),
                first_acc_address_ex,
                pt.Bytes("Payment returned"),
            )
        )
        # Else split the payment across the two accounts
        # Will panic if forward amount > deposit amount and the - would result negative
        .Else(
            send_algo_or_asa(
                pt.Btoi(first_acc_dep_asset_ex),
                pt.Btoi(first_acc_forward_amount_ex),
                second_acc_address_ex,
                pt.Bytes("Partial payment forward"),
            ),
            send_algo_or_asa(
                pt.Btoi(first_acc_dep_asset_ex),
                pt.Btoi(first_acc_dep_amount_ex) - pt.Btoi(first_acc_forward_amount_ex),
                first_acc_address_ex,
                pt.Bytes("Partial payment returned"),
            ),
        ),
        # Return first account collateral
        send_algo_or_asa(
            pt.Btoi(first_acc_col_asset_ex),
            pt.Btoi(first_acc_col_amount_ex),
            first_acc_address_ex,
            pt.Bytes("Collateral returned"),
        ),
        # Send second account deposit
        # If second_acc_deposit amount = forward amount, send to first account
        pt.If(second_acc_dep_amount_ex == second_acc_forward_amount_ex).Then(
            send_algo_or_asa(
                pt.Btoi(second_acc_dep_asset_ex),
                pt.Btoi(second_acc_dep_amount_ex),
                first_acc_address_ex,
                pt.Bytes("Payment forward"),
            )
        )
        # Elseif forward amount = 0, return to second account
        .ElseIf(pt.Btoi(second_acc_forward_amount_ex) == pt.Int(0)).Then(
            send_algo_or_asa(
                pt.Btoi(second_acc_dep_asset_ex),
                pt.Btoi(second_acc_dep_amount_ex),
                second_acc_address_ex,
                pt.Bytes("Payment returned"),
            )
        )
        # Else split the payment across the two accounts
        # Will panic if forward amount > deposit amount and the - would result negative
        .Else(
            send_algo_or_asa(
                pt.Btoi(second_acc_dep_asset_ex),
                pt.Btoi(second_acc_forward_amount_ex),
                first_acc_address_ex,
                pt.Bytes("Partial payment forward"),
            ),
            send_algo_or_asa(
                pt.Btoi(second_acc_dep_asset_ex),
                pt.Btoi(second_acc_dep_amount_ex)
                - pt.Btoi(second_acc_forward_amount_ex),
                second_acc_address_ex,
                pt.Bytes("Partial payment returned"),
            ),
        ),
        # Return second account collateral
        send_algo_or_asa(
            pt.Btoi(second_acc_col_asset_ex),
            pt.Btoi(second_acc_col_amount_ex),
            second_acc_address_ex,
            pt.Bytes("Collateral returned"),
        ),
    )


@pt.Subroutine(pt.TealType.none)
def delete_data_boxes(deal_key: pt.Expr, their_address: pt.Expr) -> pt.Expr:
    sender_data_box = pt.Concat(
        pt.Txn.sender(), pt.Extract(deal_key, pt.Int(1), pt.Int(32))
    )
    their_data_box = pt.Concat(
        their_address, pt.Extract(deal_key, pt.Int(1), pt.Int(32))
    )
    return pt.Seq(
        pt.Pop(pt.BoxDelete(sender_data_box)), pt.Pop(pt.BoxDelete(their_data_box))
    )


# Used to add addt'l txns for more box budget
@app.external
def box_budget() -> pt.Expr:
    return pt.Approve()


@app.external
def create_deal(
    deposit_payment: pt.abi.Transaction,
    collateral_payment: pt.abi.Transaction,
    key_index: pt.abi.Uint64,
    your_dep_amount: pt.abi.Uint64,
    your_dep_asset: pt.abi.Uint64,
    your_col_amount: pt.abi.Uint64,
    your_col_asset: pt.abi.Uint64,
    their_address: pt.abi.Account,
    their_key_index: pt.abi.Uint64,
    their_dep_amount: pt.abi.Uint64,
    their_dep_asset: pt.abi.Uint64,
    their_col_amount: pt.abi.Uint64,
    their_col_asset: pt.abi.Uint64,
    deal_note: pt.abi.String,
    registration_payment: pt.abi.Transaction,
    *,
    output: pt.abi.Uint64,
) -> pt.Expr:
    registration_cost_accumulator = pt.ScratchVar(pt.TealType.uint64)
    box_cost_accumulator = pt.ScratchVar(pt.TealType.uint64)
    algos_deposited_accumulator = pt.ScratchVar(pt.TealType.uint64)
    deposit_payment_txn = deposit_payment.get()
    collateral_payment_txn = collateral_payment.get()

    return pt.Seq(
        # Check that the app is active
        pt.Assert(app.state.status == pt.Bytes("active"), comment="App is active"),
        pt.Assert(
            pt.Txn.sender() != their_address.address(), comment="Addresses not equal"
        ),
        sender_abi.set(pt.Txn.sender()),
        their_address_abi.set(their_address.address()),
        # Check deposit payment vs. args
        pt.Assert(deposit_payment_txn.sender() == pt.Txn.sender()),
        pt.Assert(
            pt.Or(
                pt.And(
                    deposit_payment_txn.receiver()
                    == pt.Global.current_application_address(),
                    deposit_payment_txn.amount() == your_dep_amount.get(),
                    your_dep_asset.get() == pt.Int(0),
                ),
                pt.And(
                    deposit_payment_txn.type_enum() == pt.TxnType.AssetTransfer,
                    deposit_payment_txn.asset_receiver()
                    == pt.Global.current_application_address(),
                    deposit_payment_txn.asset_amount() == your_dep_amount.get(),
                    deposit_payment_txn.xfer_asset() == your_dep_asset.get(),
                ),
            )
        ),
        # Check collateral payment vs. args
        pt.Assert(collateral_payment_txn.sender() == pt.Txn.sender()),
        pt.Assert(
            pt.Or(
                pt.And(
                    collateral_payment_txn.receiver()
                    == pt.Global.current_application_address(),
                    collateral_payment_txn.amount() == your_col_amount.get(),
                    your_col_asset.get() == pt.Int(0),
                ),
                pt.And(
                    # collateral_payment_txn.type_enum() == pt.TxnType.AssetTransfer,
                    collateral_payment_txn.asset_receiver()
                    == pt.Global.current_application_address(),
                    collateral_payment_txn.asset_amount() == your_col_amount.get(),
                    collateral_payment_txn.xfer_asset() == your_col_asset.get(),
                ),
            )
        ),
        # Verify the length of the method arguments
        pt.Assert(
            pt.Len(your_dep_amount.encode()) == pt.Int(8),
            comment="your_dep_amount length=32",
        ),
        pt.Assert(
            pt.Len(your_dep_asset.encode()) == pt.Int(8),
            comment="your_dep_asset length=32",
        ),
        pt.Assert(
            pt.Len(your_col_amount.encode()) == pt.Int(8),
            comment="your_col_amount length=32",
        ),
        pt.Assert(
            pt.Len(your_col_asset.encode()) == pt.Int(8),
            comment="your_col_asset length=32",
        ),
        pt.Assert(
            pt.Len(their_dep_amount.encode()) == pt.Int(8),
            comment="their_dep_amount length=32",
        ),
        pt.Assert(
            pt.Len(their_dep_asset.encode()) == pt.Int(8),
            comment="their_dep_asset length=32",
        ),
        pt.Assert(
            pt.Len(their_col_amount.encode()) == pt.Int(8),
            comment="their_col_amount length=32",
        ),
        pt.Assert(
            pt.Len(their_col_asset.encode()) == pt.Int(8),
            comment="their_col_asset length=32",
        ),
        pt.Assert(
            pt.Len(deal_note.get()) <= pt.Int(874),
            comment="deal_note string length<=872",
        ),  # for 1024 byte deal box
        # Check that no deal key exists for these two accounts + deal note
        deal_key.store(create_deal_key(their_address.address(), deal_note.get())),
        pt.Assert(
            all_deal_boxes[deal_key.load()].exists() == pt.Int(0),
            comment="Deal does not already exist",
        ),
        # Build the deal value
        (first_acc_data := pt.abi.Byte()).set(pt.Int(0)),
        (second_acc_data := pt.abi.Byte()).set(pt.Int(0)),
        # Whichever account is "greater" is the first account
        pt.If(pt.BytesGt(pt.Txn.sender(), their_address.address()))
        # Sender account is "greater" so goes first
        .Then(
            # Set status to 1 for a new pending deposit as no existing deal was found
            (first_acc_status := pt.abi.Byte()).set(pt.Int(1)),
            (second_acc_status := pt.abi.Byte()).set(pt.Int(0)),
            (new_deal_value := DealValue()).set(
                first_acc_status,
                second_acc_status,
                sender_abi,
                your_dep_amount,
                your_dep_asset,
                your_col_amount,
                your_col_asset,
                their_address_abi,
                their_dep_amount,
                their_dep_asset,
                their_col_amount,
                their_col_asset,
                # Again, first account goes first
                your_dep_amount,  # Default 1st acc payment forward amt to deposit amt
                their_dep_amount,  # Default 2nd acc payment forward amt to deposit amt
                first_acc_data,
                second_acc_data,
                deal_note,
            ),
            # Store the deal
            all_deal_boxes[deal_key.load()].set(new_deal_value),
        )
        # Sender account is "less" so goes second
        .Else(
            # Set status to 1 for a new pending deposit as no existing deal was found
            (first_acc_status := pt.abi.Byte()).set(pt.Int(0)),
            (second_acc_status := pt.abi.Byte()).set(pt.Int(1)),
            (new_deal_value := DealValue()).set(
                first_acc_status,
                second_acc_status,
                their_address_abi,
                their_dep_amount,
                their_dep_asset,
                their_col_amount,
                their_col_asset,
                sender_abi,
                your_dep_amount,
                your_dep_asset,
                your_col_amount,
                your_col_asset,
                # Again, first account goes first
                their_dep_amount,  # Default 1st acc payment forward amt to deposit amt
                your_dep_amount,  # Default 2nd acc payment forward amt to deposit amt
                first_acc_data,
                second_acc_data,
                deal_note,
            ),
            # Store the deal
            all_deal_boxes[deal_key.load()].set(new_deal_value),
        ),
        # Start counting the cost of registrations
        registration_cost_accumulator.store(pt.Int(0)),
        # Start counting the cost of boxes created
        box_cost_accumulator.store(pt.Int(0)),
        algos_deposited_accumulator.store(pt.Int(0)),
        deal_box_length := pt.BoxLen(deal_key.load()),
        pt.Assert(deal_box_length.hasValue(), comment="deal_box_length"),
        box_cost_accumulator.store(
            pt.Int(BoxFlatMBR)
            + (
                pt.Int(BoxByteMBR)
                * (deal_box_length.value() + pt.Int(DealDetailsKeyLength))
            )
        ),
        # Add the deal to both accounts' deals list
        record_deal_key(
            pt.Txn.sender(),
            deal_key.load(),
            key_index.get(),
            registration_cost_accumulator,
        ),
        record_deal_key(
            their_address.address(),
            deal_key.load(),
            their_key_index.get(),
            registration_cost_accumulator,
        ),
        pt.If(deposit_payment_txn.type_enum() == pt.TxnType.Payment).Then(
            algos_deposited_accumulator.store(deposit_payment_txn.amount())
        ),
        pt.If(collateral_payment_txn.type_enum() == pt.TxnType.Payment).Then(
            algos_deposited_accumulator.store(
                algos_deposited_accumulator.load() + collateral_payment_txn.amount()
            )
        ),
        # Check that registration payment = registrations cost
        # Requiring registration cost also disincentivizes spam
        pt.If(registration_cost_accumulator.load() > pt.Int(0)).Then(
            pt.Seq(
                pt.Assert(
                    registration_payment.get().receiver()
                    == pt.Global.current_application_address(),
                    comment="Registration payment receiver is app address",
                ),
                pt.Assert(
                    registration_cost_accumulator.load()
                    == registration_payment.get().amount(),
                    comment="Registrations cost = Algos paid",
                ),
            ),
        ),
        # Check that deposited Algos > box cost
        pt.Assert(
            box_cost_accumulator.load() <= algos_deposited_accumulator.load(),
            comment="Created boxes cost < Algos deposited",
        ),
        output.set(box_cost_accumulator.load()),
    )


@app.external
def attach_data(
    deal_key: DealKey,  # 33
    key_index: pt.abi.Uint64,  # 8
    data_length: pt.abi.Uint64,  # 8
    data_index: pt.abi.Uint64,  # 8
    data: pt.abi.String,  # 1984 max?
    *,
    output: pt.abi.Uint64,
) -> pt.Expr:
    data_key = pt.ScratchVar(pt.TealType.bytes)
    box_cost_accumulator = pt.ScratchVar(pt.TealType.uint64)
    algos_deposited_accumulator = pt.ScratchVar(pt.TealType.uint64)

    return pt.Seq(
        # Check that the app is active
        pt.Assert(app.state.status == pt.Bytes("active"), comment="App is active"),
        box_cost_accumulator.store(pt.Int(0)),
        algos_deposited_accumulator.store(pt.Int(0)),
        data_key.store(
            pt.Concat(
                pt.Txn.sender(), pt.Extract(deal_key.get(), pt.Int(1), pt.Int(32))
            )
        ),
        # Confirm deal box is in sender key list
        pt.Assert(
            confirm_deal_key_at_index(pt.Txn.sender(), deal_key.get(), key_index.get()),
            comment="Given key is in sender's key list",
        ),
        deal_details := pt.BoxGet(deal_key.get()),
        pt.Assert(deal_details.hasValue()),
        deal_value.store(deal_details.value()),
        # If sender is first account
        pt.If(pt.Txn.sender() == first_acc_address_ex).Then(
            pt.Assert(
                pt.Or(
                    first_acc_status_ex == pt.Bytes("base16", "0x01"),
                    first_acc_status_ex == pt.Bytes("base16", "0x02"),
                    first_acc_status_ex == pt.Bytes("base16", "0x03"),
                ),
                comment="first_acc_status=0x01 or 0x02 or 0x03",
            ),
            pt.If(pt.Btoi(first_acc_dep_asset_ex) == pt.Int(0)).Then(
                algos_deposited_accumulator.store(pt.Btoi(first_acc_dep_amount_ex))
            ),
            pt.If(pt.Btoi(first_acc_col_asset_ex) == pt.Int(0)).Then(
                algos_deposited_accumulator.store(
                    algos_deposited_accumulator.load()
                    + pt.Btoi(first_acc_col_amount_ex)
                )
            ),
            pt.BoxReplace(deal_key.get(), pt.Int(146), pt.Bytes("base16", "0x01")),
        )
        # If sender is second account
        .ElseIf(pt.Txn.sender() == second_acc_address_ex).Then(
            pt.Assert(
                pt.Or(
                    second_acc_status_ex == pt.Bytes("base16", "0x01"),
                    second_acc_status_ex == pt.Bytes("base16", "0x02"),
                    second_acc_status_ex == pt.Bytes("base16", "0x03"),
                ),
                comment="second_acc_status=0x01 or 0x02 or 0x03",
            ),
            pt.If(pt.Btoi(second_acc_dep_asset_ex) == pt.Int(0)).Then(
                algos_deposited_accumulator.store(pt.Btoi(second_acc_dep_amount_ex))
            ),
            pt.If(pt.Btoi(second_acc_col_asset_ex) == pt.Int(0)).Then(
                algos_deposited_accumulator.store(
                    algos_deposited_accumulator.load()
                    + pt.Btoi(second_acc_col_amount_ex)
                )
            ),
            pt.BoxReplace(deal_key.get(), pt.Int(147), pt.Bytes("base16", "0x01")),
        )
        # If sender matches neither deal address, reject
        .Else(pt.Reject()),
        # Check if data box already exists
        data_box_length := pt.BoxLen(data_key.load()),
        pt.If(data_box_length.hasValue())
        # If so, put the data in the box at the given index
        .Then(
            pt.Pop(data_box_length.value()),
            pt.BoxReplace(data_key.load(), data_index.get(), data.get()),
        )
        # If not, create a box of the given length and insert data at the given index
        .Else(
            box_cost_accumulator.store(
                (
                    (
                        (data_length.get() + pt.Int(DealDataKeyLength))
                        * pt.Int(BoxByteMBR)
                    )
                    + pt.Int(BoxFlatMBR)
                )
                + pt.Int(DealDetailsCost)
            ),
            pt.Assert(
                box_cost_accumulator.load() <= algos_deposited_accumulator.load(),
                comment="Algos in deal exceed cost of new box + 3 deal boxes",
            ),
            pt.Pop(pt.BoxCreate(data_key.load(), data_length.get())),
            pt.BoxReplace(data_key.load(), data_index.get(), data.get()),
        ),
        output.set(box_cost_accumulator.load()),
    )


@app.external
def match_deal(
    deposit_payment: pt.abi.Transaction,
    collateral_payment: pt.abi.Transaction,
    deal_key: DealKey,
    key_index: pt.abi.Uint64,
    their_address: pt.abi.Account,
    their_key_index: pt.abi.Uint64,
    *,
    output: pt.abi.StaticBytes[Literal[2]],
) -> pt.Expr:
    deposit_payment_txn = deposit_payment.get()
    collateral_payment_txn = collateral_payment.get()

    return pt.Seq(
        pt.Assert(deposit_payment_txn.sender() == pt.Txn.sender()),
        pt.Assert(collateral_payment_txn.sender() == pt.Txn.sender()),
        check_deal_keys(
            deal_key.get(),
            key_index.get(),
            their_address.address(),
            their_key_index.get(),
        ),
        # Extract the deal terms from the deal box and store in deal_value
        pt.Assert(all_deal_boxes[deal_key].exists(), comment="deal_value has value"),
        deal_value.store(all_deal_boxes[deal_key].get()),
        # Check that sender status is 0 and counterparty is 1
        pt.If(pt.BytesGt(pt.Txn.sender(), their_address.address()))
        # If sender is the first account
        .Then(
            pt.Assert(
                first_acc_status_ex == pt.Bytes("base16", "0x00"),
                comment="first_acc_status=0x00",
            ),
            pt.Assert(
                second_acc_status_ex == pt.Bytes("base16", "0x01"),
                comment="second_acc_status=0x01",
            ),
            # Check deposit vs. deal first acc details
            pt.If(first_acc_dep_asset_ex == pt.Itob(pt.Int(0)))
            .Then(
                pt.Assert(
                    deposit_payment_txn.receiver()
                    == pt.Global.current_application_address()
                ),
                pt.Assert(
                    pt.Itob(deposit_payment_txn.amount()) == first_acc_dep_amount_ex
                ),
            )
            .Else(
                pt.Assert(deposit_payment_txn.type_enum() == pt.TxnType.AssetTransfer),
                pt.Assert(
                    deposit_payment_txn.asset_receiver()
                    == pt.Global.current_application_address()
                ),
                pt.Assert(
                    pt.Itob(deposit_payment_txn.asset_amount())
                    == first_acc_dep_amount_ex
                ),
                pt.Assert(
                    pt.Itob(deposit_payment_txn.xfer_asset()) == first_acc_dep_asset_ex
                ),
            ),
            # Check collateral vs. deal first acc details
            pt.If(first_acc_col_asset_ex == pt.Itob(pt.Int(0)))
            .Then(
                pt.Assert(
                    collateral_payment_txn.receiver()
                    == pt.Global.current_application_address()
                ),
                pt.Assert(
                    pt.Itob(collateral_payment_txn.amount()) == first_acc_col_amount_ex
                ),
            )
            .Else(
                pt.Assert(
                    collateral_payment_txn.type_enum() == pt.TxnType.AssetTransfer
                ),
                pt.Assert(
                    collateral_payment_txn.asset_receiver()
                    == pt.Global.current_application_address()
                ),
                pt.Assert(
                    pt.Itob(collateral_payment_txn.asset_amount())
                    == first_acc_col_amount_ex
                ),
                pt.Assert(
                    pt.Itob(collateral_payment_txn.xfer_asset())
                    == first_acc_col_asset_ex
                ),
            ),
        )
        # If the sender if the second account
        .Else(
            pt.Assert(
                first_acc_status_ex == pt.Bytes("base16", "0x01"),
                comment="first_acc_status=0x01",
            ),
            pt.Assert(
                second_acc_status_ex == pt.Bytes("base16", "0x00"),
                comment="second_acc_status=0x00",
            ),
            # Check deposit vs. deal second acc details
            pt.If(second_acc_dep_asset_ex == pt.Itob(pt.Int(0)))
            .Then(
                pt.Assert(
                    deposit_payment_txn.receiver()
                    == pt.Global.current_application_address()
                ),
                pt.Assert(
                    pt.Itob(deposit_payment_txn.amount()) == second_acc_dep_amount_ex
                ),
            )
            .Else(
                pt.Assert(deposit_payment_txn.type_enum() == pt.TxnType.AssetTransfer),
                pt.Assert(
                    deposit_payment_txn.asset_receiver()
                    == pt.Global.current_application_address()
                ),
                pt.Assert(
                    pt.Itob(deposit_payment_txn.asset_amount())
                    == second_acc_dep_amount_ex
                ),
                pt.Assert(
                    pt.Itob(deposit_payment_txn.xfer_asset()) == second_acc_dep_asset_ex
                ),
            ),
            # Check collateral vs. deal second acc details
            pt.If(second_acc_col_asset_ex == pt.Itob(pt.Int(0)))
            .Then(
                pt.Assert(
                    collateral_payment_txn.receiver()
                    == pt.Global.current_application_address()
                ),
                pt.Assert(
                    pt.Itob(collateral_payment_txn.amount()) == second_acc_col_amount_ex
                ),
            )
            .Else(
                pt.Assert(
                    collateral_payment_txn.type_enum() == pt.TxnType.AssetTransfer
                ),
                pt.Assert(
                    collateral_payment_txn.asset_receiver()
                    == pt.Global.current_application_address()
                ),
                pt.Assert(
                    pt.Itob(collateral_payment_txn.asset_amount())
                    == second_acc_col_amount_ex
                ),
                pt.Assert(
                    pt.Itob(collateral_payment_txn.xfer_asset())
                    == second_acc_col_asset_ex
                ),
            ),
        ),
        # Update deal status in deal box to 2 (0x02) meaning locked
        (first_acc_status := pt.abi.Byte()).set(pt.Int(2)),
        (second_acc_status := pt.abi.Byte()).set(pt.Int(2)),
        pt.BoxReplace(
            deal_key.get(),
            pt.Int(0),
            pt.Concat(first_acc_status.encode(), second_acc_status.encode()),
        ),
        # Increment total_deals and active_deals counters
        app.state.total_deals.set(app.state.total_deals + pt.Int(1)),
        app.state.active_deals.set(app.state.active_deals + pt.Int(1)),
        output.set(pt.Concat(first_acc_status.encode(), second_acc_status.encode())),
    )


@app.external
def recall_deal(
    deal_key: DealKey,
    key_index: pt.abi.Uint64,
    their_address: pt.abi.Account,
    their_key_index: pt.abi.Uint64,
    *,
    output: pt.abi.String,
) -> pt.Expr:
    return pt.Seq(
        check_deal_keys(
            deal_key.get(),
            key_index.get(),
            their_address.address(),
            their_key_index.get(),
        ),
        # Extract the deal terms from the deal box and store in deal_value
        pt.Assert(all_deal_boxes[deal_key].exists(), comment="deal_value has value"),
        deal_value.store(all_deal_boxes[deal_key].get()),
        # If sender account is first
        pt.If(pt.BytesGt(pt.Txn.sender(), their_address.address())).Then(
            # Check your status is 1 and theirs is 0
            pt.Assert(
                first_acc_status_ex == pt.Bytes("base16", "0x01"),
                comment="first_acc_status=0x01",
            ),
            pt.Assert(
                second_acc_status_ex == pt.Bytes("base16", "0x00"),
                comment="second_acc_status=0x00",
            ),
            # Return the first account deposit & coll
            send_algo_or_asa(
                pt.Btoi(first_acc_dep_asset_ex),
                pt.Btoi(first_acc_dep_amount_ex),
                first_acc_address_ex,
                pt.Bytes("Deal recalled"),
            ),
            send_algo_or_asa(
                pt.Btoi(first_acc_col_asset_ex),
                pt.Btoi(first_acc_col_amount_ex),
                first_acc_address_ex,
                pt.Bytes("Deal recalled"),
            ),
        )
        # If sender account is second
        .Else(
            # Check your status is 1 and theirs is 0
            pt.Assert(
                first_acc_status_ex == pt.Bytes("base16", "0x00"),
                comment="first_acc_status=0x00",
            ),
            pt.Assert(
                second_acc_status_ex == pt.Bytes("base16", "0x01"),
                comment="second_acc_status=0x01",
            ),
            # Return the second deposit & coll
            send_algo_or_asa(
                pt.Btoi(second_acc_dep_asset_ex),
                pt.Btoi(second_acc_dep_amount_ex),
                second_acc_address_ex,
                pt.Bytes("Deal recalled"),
            ),
            send_algo_or_asa(
                pt.Btoi(second_acc_col_asset_ex),
                pt.Btoi(second_acc_col_amount_ex),
                second_acc_address_ex,
                pt.Bytes("Deal recalled"),
            ),
        ),
        # Delete the deal box keys from both accounts
        erase_deal_key_at_index(pt.Txn.sender(), key_index.get()),
        erase_deal_key_at_index(their_address.address(), their_key_index.get()),
        # Delete deal box
        pt.Pop(all_deal_boxes[deal_key].delete()),
        # Delete data boxes for both accounts for this deal
        delete_data_boxes(deal_key.get(), their_address.address()),
        output.set(pt.Bytes("Recalled")),
    )


@app.external
def reject_deal(
    deal_key: DealKey,
    key_index: pt.abi.Uint64,
    their_address: pt.abi.Account,
    their_key_index: pt.abi.Uint64,
    *,
    output: pt.abi.String,
) -> pt.Expr:
    return pt.Seq(
        check_deal_keys(
            deal_key.get(),
            key_index.get(),
            their_address.address(),
            their_key_index.get(),
        ),
        # Extract the deal terms from the deal box and store in deal_value
        pt.Assert(all_deal_boxes[deal_key].exists(), comment="deal_value has value"),
        deal_value.store(all_deal_boxes[deal_key].get()),
        # If sender account is first
        pt.If(pt.BytesGt(pt.Txn.sender(), their_address.address())).Then(
            # Check your status is 0 and theirs is 1
            pt.Assert(
                first_acc_status_ex == pt.Bytes("base16", "0x00"),
                comment="first_acc_status=0x00",
            ),
            pt.Assert(
                second_acc_status_ex == pt.Bytes("base16", "0x01"),
                comment="second_acc_status=0x01",
            ),
            # Return the second account deposit & coll
            send_algo_or_asa(
                pt.Btoi(second_acc_dep_asset_ex),
                pt.Btoi(second_acc_dep_amount_ex),
                second_acc_address_ex,
                pt.Concat(pt.Bytes("Deal rejected by "), pt.Txn.sender()),
            ),
            send_algo_or_asa(
                pt.Btoi(second_acc_col_asset_ex),
                pt.Btoi(second_acc_col_amount_ex),
                second_acc_address_ex,
                pt.Concat(pt.Bytes("Deal rejected by "), pt.Txn.sender()),
            ),
        )
        # If sender account is second
        .Else(
            # Check your status is 0 and theirs is 1
            pt.Assert(
                first_acc_status_ex == pt.Bytes("base16", "0x01"),
                comment="first_acc_status=0x01",
            ),
            pt.Assert(
                second_acc_status_ex == pt.Bytes("base16", "0x00"),
                comment="second_acc_status=0x00",
            ),
            # Return the first deposit & coll
            send_algo_or_asa(
                pt.Btoi(first_acc_dep_asset_ex),
                pt.Btoi(first_acc_dep_amount_ex),
                first_acc_address_ex,
                pt.Concat(pt.Bytes("Deal rejected by "), pt.Txn.sender()),
            ),
            send_algo_or_asa(
                pt.Btoi(first_acc_col_asset_ex),
                pt.Btoi(first_acc_col_amount_ex),
                first_acc_address_ex,
                pt.Concat(pt.Bytes("Deal rejected by "), pt.Txn.sender()),
            ),
        ),
        # Delete the deal box keys from both accounts
        erase_deal_key_at_index(pt.Txn.sender(), key_index.get()),
        erase_deal_key_at_index(their_address.address(), their_key_index.get()),
        # Delete deal box
        pt.Pop(all_deal_boxes[deal_key].delete()),
        # Delete data boxes for both accounts for this deal
        delete_data_boxes(deal_key.get(), their_address.address()),
        output.set(pt.Bytes("Rejected")),
    )


@app.external
def adjust_disbursement(
    deal_key: DealKey,
    key_index: pt.abi.Uint64,
    their_address: pt.abi.Account,
    their_key_index: pt.abi.Uint64,
    first_acc_forward_amount: pt.abi.Uint64,
    second_acc_forward_amount: pt.abi.Uint64,
    *,
    output: pt.abi.String,
) -> pt.Expr:
    return pt.Seq(
        check_deal_keys(
            deal_key.get(),
            key_index.get(),
            their_address.address(),
            their_key_index.get(),
        ),
        # Verify the length of the method arguments
        pt.Assert(
            pt.Len(first_acc_forward_amount.encode()) == pt.Int(8),
            comment="first_acc_forward_amount length=8",
        ),
        pt.Assert(
            pt.Len(second_acc_forward_amount.encode()) == pt.Int(8),
            comment="second_acc_forward_amount length=8",
        ),
        # Extract the deal terms from the deal box and store in deal_value
        pt.Assert(all_deal_boxes[deal_key].exists(), comment="deal_value has value"),
        deal_value.store(all_deal_boxes[deal_key].get()),
        # Check sender status is 2 or 3
        pt.Assert(
            pt.Or(
                first_acc_status_ex == pt.Bytes("base16", "0x02"),
                first_acc_status_ex == pt.Bytes("base16", "0x03"),
            ),
            comment="first_acc_status=0x02 or 0x03",
        ),
        # Check their status is 2 or 3
        pt.Assert(
            pt.Or(
                second_acc_status_ex == pt.Bytes("base16", "0x02"),
                second_acc_status_ex == pt.Bytes("base16", "0x03"),
            ),
            comment="second_acc_status=0x02 or 0x03",
        ),
        # If sender is the first account
        pt.If(pt.BytesGt(pt.Txn.sender(), their_address.address())).Then(
            # Set your status to 3 and theirs to 2
            (first_acc_status := pt.abi.Byte()).set(pt.Int(3)),
            (second_acc_status := pt.abi.Byte()).set(pt.Int(2)),
            pt.BoxReplace(
                deal_key.get(),
                pt.Int(0),
                pt.Concat(first_acc_status.encode(), second_acc_status.encode()),
            ),
        )
        # If sender is the second account
        .Else(
            # Set your status to 3 and theirs to 2
            (first_acc_status := pt.abi.Byte()).set(pt.Int(2)),
            (second_acc_status := pt.abi.Byte()).set(pt.Int(3)),
            pt.BoxReplace(
                deal_key.get(),
                pt.Int(0),
                pt.Concat(first_acc_status.encode(), second_acc_status.encode()),
            ),
        ),
        # Either way, we are overwriting the forward payment amounts into the box
        pt.BoxReplace(
            deal_key.get(),
            pt.Int(130),
            pt.Concat(
                first_acc_forward_amount.encode(),
                second_acc_forward_amount.encode(),
            ),
        ),
        output.set(pt.Bytes("Adjusted")),
    )


@app.external
def agree_disbursement(
    deal_key: DealKey,
    key_index: pt.abi.Uint64,
    their_address: pt.abi.Account,
    their_key_index: pt.abi.Uint64,
    *,
    output: pt.abi.String,
) -> pt.Expr:
    return pt.Seq(
        check_deal_keys(
            deal_key.get(),
            key_index.get(),
            their_address.address(),
            their_key_index.get(),
        ),
        # Extract the deal terms from the deal box and store in deal_value
        pt.Assert(all_deal_boxes[deal_key].exists(), comment="deal_value has value"),
        deal_value.store(all_deal_boxes[deal_key].get()),
        ###
        # If sender is the first account
        pt.If(pt.BytesGt(pt.Txn.sender(), their_address.address()))
        # Check sender status is 2
        .Then(
            pt.Assert(
                first_acc_status_ex == pt.Bytes("base16", "0x02"),
                comment="first_acc_status=0x02",
            ),
            # If their status is 2, update sender status to 3
            pt.If(second_acc_status_ex == pt.Bytes("base16", "0x02")).Then(
                (first_acc_status := pt.abi.Byte()).set(pt.Int(3)),
                pt.BoxReplace(deal_key.get(), pt.Int(0), first_acc_status.encode()),
            )
            # If their status is 3, disburse
            .ElseIf(second_acc_status_ex == pt.Bytes("base16", "0x03")).Then(
                send_disbursements(),
                # Delete deal box keys from both accounts and then the deal box itself
                erase_deal_key_at_index(pt.Txn.sender(), key_index.get()),
                erase_deal_key_at_index(their_address.address(), their_key_index.get()),
                # Delete deal box and data boxes for both accounts for this deal
                pt.Pop(all_deal_boxes[deal_key].delete()),
                delete_data_boxes(deal_key.get(), their_address.address()),
                # Decrement active_deals counter
                app.state.active_deals.set(app.state.active_deals - pt.Int(1)),
                # Increment completed_deals counter
                app.state.completed_deals.set(app.state.completed_deals + pt.Int(1)),
                output.set(pt.Bytes("Disbursed")),
            )
            # Otherwise reject
            .Else(pt.Reject()),
        )
        ###
        # If sender is the second account
        .Else(
            pt.Assert(
                second_acc_status_ex == pt.Bytes("base16", "0x02"),
                comment="first_acc_status=0x02",
            ),
            # If their status is 2, update sender status to 3
            pt.If(first_acc_status_ex == pt.Bytes("base16", "0x02")).Then(
                (second_acc_status := pt.abi.Byte()).set(pt.Int(3)),
                pt.BoxReplace(deal_key.get(), pt.Int(1), second_acc_status.encode()),
            )
            # If their status is 3, disburse
            .ElseIf(first_acc_status_ex == pt.Bytes("base16", "0x03")).Then(
                send_disbursements(),
                # Delete deal box keys from both accounts and then the deal box itself
                erase_deal_key_at_index(pt.Txn.sender(), key_index.get()),
                erase_deal_key_at_index(their_address.address(), their_key_index.get()),
                # Delete deal box and data boxes for both accounts for this deal
                pt.Pop(all_deal_boxes[deal_key].delete()),
                delete_data_boxes(deal_key.get(), their_address.address()),
                # Decrement active_deals counter
                app.state.active_deals.set(app.state.active_deals - pt.Int(1)),
                # Increment completed_deals counter
                app.state.completed_deals.set(app.state.completed_deals + pt.Int(1)),
                output.set(pt.Bytes("Disbursed")),
            )
            # Otherwise reject
            .Else(pt.Reject()),
        ),
    )
