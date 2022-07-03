from pyteal import *


@Subroutine(TealType.none)
def check_accounts():
    """Checks the accounts in the app call and atomic group for integrity"""
    return Seq(
        Assert(Txn.accounts.length() == Int(1)),  # Only 2 Ac in the Acs array
        Assert(Txn.accounts[0] != Txn.accounts[1]),  # Acs must be different
        Assert(Txn.accounts[0] != Global.zero_address()),  # Depositor Ac not 0
        Assert(Txn.accounts[1] != Global.zero_address()),  # Beneficiary Ac not 0
    )


@Subroutine(TealType.none)
def check_deposit_fee_payment():
    """Checks that the fourth transaction in the atomic group is an ALGO payment
    to the application to cover fees"""
    return Seq(
        Assert(Gtxn[3].receiver() == Global.current_application_address()),
        Assert(Gtxn[3].type_enum() == Int(1)),
        Assert(
            Gtxn[3].amount()
            == (
                App.globalGet(Bytes("base_fee"))
                # + (Txn.assets.length() * Global.min_balance())  # Optional charge to opt into ASAs
            )
        ),
    )


@Subroutine(TealType.none)
def create_pending_deposit():
    """Writes deposit details into local state"""
    return Seq(
        # Write to depositor's local storage only and set status to 1 for pending
        App.localPut(d_addr.load(), Bytes("status"), Int(1)),
        App.localPut(d_addr.load(), Bytes("theirAddress"), b_addr.load()),
        App.localPut(d_addr.load(), Bytes("yourDepositAsset"), d_dep_asset.load()),
        App.localPut(d_addr.load(), Bytes("yourDepositAmount"), d_dep_amt.load()),
        App.localPut(d_addr.load(), Bytes("yourCollateralAsset"), d_col_asset.load()),
        App.localPut(d_addr.load(), Bytes("yourCollateralAmount"), d_col_amt.load()),
        App.localPut(d_addr.load(), Bytes("theirDepositAsset"), b_dep_asset.load()),
        App.localPut(d_addr.load(), Bytes("theirDepositAmount"), b_dep_amt.load()),
        App.localPut(d_addr.load(), Bytes("theirCollateralAsset"), b_col_asset.load()),
        App.localPut(d_addr.load(), Bytes("theirCollateralAmount"), b_col_amt.load()),
        App.localPut(d_addr.load(), Bytes("note"), note.load()),
        Log(Bytes("Deposit pending confirmation")),
    )


@Subroutine(TealType.none)
def check_deposit_details():
    """Checks the details of the deposit against the counterparty local state"""
    return Seq(
        # Check all app args against the counterparty's local state
        Assert(
            d_dep_asset.load()
            == App.localGet(b_addr.load(), Bytes("theirDepositAsset"))
        ),
        Assert(
            d_dep_amt.load() == App.localGet(b_addr.load(), Bytes("theirDepositAmount"))
        ),
        Assert(
            d_col_asset.load()
            == App.localGet(b_addr.load(), Bytes("theirCollateralAsset"))
        ),
        Assert(
            d_col_amt.load()
            == App.localGet(b_addr.load(), Bytes("theirCollateralAmount"))
        ),
        Assert(
            b_dep_asset.load() == App.localGet(b_addr.load(), Bytes("yourDepositAsset"))
        ),
        Assert(
            b_dep_amt.load() == App.localGet(b_addr.load(), Bytes("yourDepositAmount"))
        ),
        Assert(
            b_col_asset.load()
            == App.localGet(b_addr.load(), Bytes("yourCollateralAsset"))
        ),
        Assert(
            b_col_amt.load()
            == App.localGet(b_addr.load(), Bytes("yourCollateralAmount"))
        ),
        # There is no assert to check the note; it is OK if the note doesnt match
    )


@Subroutine(TealType.none)
def lock_in_deposit():
    """Writes deposit details into local state and locks the deposit"""
    return Seq(
        # Write terms into sender's local state
        App.localPut(d_addr.load(), Bytes("theirAddress"), b_addr.load()),
        App.localPut(d_addr.load(), Bytes("yourDepositAsset"), d_dep_asset.load()),
        App.localPut(d_addr.load(), Bytes("yourDepositAmount"), d_dep_amt.load()),
        App.localPut(d_addr.load(), Bytes("yourCollateralAsset"), d_col_asset.load()),
        App.localPut(d_addr.load(), Bytes("yourCollateralAmount"), d_col_amt.load()),
        App.localPut(d_addr.load(), Bytes("theirDepositAsset"), b_dep_asset.load()),
        App.localPut(d_addr.load(), Bytes("theirDepositAmount"), b_dep_amt.load()),
        App.localPut(d_addr.load(), Bytes("theirCollateralAsset"), b_col_asset.load()),
        App.localPut(d_addr.load(), Bytes("theirCollateralAmount"), b_col_amt.load()),
        # Write the sender's note into their local state
        App.localPut(d_addr.load(), Bytes("note"), note.load()),
        # Then set both accounts' status to 2 for locked
        App.localPut(d_addr.load(), Bytes("status"), Int(2)),
        App.localPut(b_addr.load(), Bytes("status"), Int(2)),
        Log(Bytes("Escrow locked")),
    )


@Subroutine(TealType.none)
def opt_into_asa(asset: Expr):
    """Checks if the contract holds an asset in the transaction assets array
    and, if not, opts into it and increments the escrow_fees value.

    Args:
        asset_id: A uint64 which can be 0 to represent ALGO or a valid ASA ID
    """
    asset_balance = AssetHolding.balance(Global.current_application_address(), asset)
    return Seq(
        asset_balance,
        If(asset_balance.hasValue() == Int(0)).Then(
            send_algo_or_asa(asset, Int(0), Global.current_application_address()),
        ),
    )


@Subroutine(TealType.none)
def send_algo_or_asa(asset_id: Expr, amount: Expr, account: Expr):
    """Builds an InnerTxn dynamically as a payment or asset transfer
    depending on the asset_id

    Args:
        asset_id: A uint64 which can be 0 to represent ALGO or a valid ASA ID
        amount: A uint64 quantity amount for the payment or asset transfer
        account: The receiving account as a PyTeal expression
    """
    return Seq(
        If(asset_id == Int(0))
        .Then(
            Seq(
                InnerTxnBuilder.Begin(),
                InnerTxnBuilder.SetFields(
                    {
                        TxnField.type_enum: TxnType.Payment,
                        TxnField.amount: amount,
                        TxnField.receiver: account,
                    }
                ),
                InnerTxnBuilder.Submit(),
            )
        )
        .Else(
            Seq(
                InnerTxnBuilder.Begin(),
                InnerTxnBuilder.SetFields(
                    {
                        TxnField.type_enum: TxnType.AssetTransfer,
                        TxnField.xfer_asset: asset_id,
                        TxnField.asset_amount: amount,
                        TxnField.asset_receiver: account,
                    }
                ),
                InnerTxnBuilder.Submit(),
            )
        ),
        Log(Bytes("InnerTxn sent")),
    )


# Setting up scratch space slots
d_addr = ScratchVar(TealType.bytes)
d_dep_asset = ScratchVar(TealType.uint64)
d_dep_amt = ScratchVar(TealType.uint64)
d_col_asset = ScratchVar(TealType.uint64)
d_col_amt = ScratchVar(TealType.uint64)
b_addr = ScratchVar(TealType.bytes)
b_dep_asset = ScratchVar(TealType.uint64)
b_dep_amt = ScratchVar(TealType.uint64)
b_col_asset = ScratchVar(TealType.uint64)
b_col_amt = ScratchVar(TealType.uint64)
note = ScratchVar(TealType.bytes)
return_to_you_amt = ScratchVar(TealType.uint64)
send_to_them_amt = ScratchVar(TealType.uint64)
you_receive_amt = ScratchVar(TealType.uint64)
return_to_them_amt = ScratchVar(TealType.uint64)
i = ScratchVar(TealType.uint64)


def approval_program():
    """The application's working logic is defined here"""

    b_app_status = App.localGetEx(
        Txn.accounts[1], Global.current_application_id(), Bytes("status")
    )

    on_create = Seq(
        App.globalPut(
            Bytes("app_status"), Int(0)
        ),  # App is disabled by default for safety after deployment
        App.globalPut(Bytes("base_fee"), Int(1_000_000)),
        Approve(),
    )

    on_deposit = Seq(
        Assert(App.globalGet(Bytes("app_status")) == Int(1)),
        check_accounts(),
        d_addr.store(Txn.accounts[0]),
        d_dep_asset.store(Btoi(Txn.application_args[1])),
        d_dep_amt.store(Btoi(Txn.application_args[2])),
        d_col_asset.store(Btoi(Txn.application_args[3])),
        d_col_amt.store(Btoi(Txn.application_args[4])),
        b_addr.store(Txn.accounts[1]),
        b_dep_asset.store(Btoi(Txn.application_args[5])),
        b_dep_amt.store(Btoi(Txn.application_args[6])),
        b_col_asset.store(Btoi(Txn.application_args[7])),
        b_col_amt.store(Btoi(Txn.application_args[8])),
        note.store(Txn.application_args[9]),
        # Initial checks
        check_deposit_fee_payment(),
        # Checks that the sending acc's indicator is set to 4 for no active deal
        # Later on, if the counterparty has already alleged, the deal will be locked in
        Assert(App.localGet(Txn.accounts[0], Bytes("status")) == Int(4)),
        # Opt into any ASAs in the Txn.assets array
        # Check the transaction group against the app args
        # Checking the depositor's deposit vs Gtxn[1]
        Assert(Gtxn[1].sender() == d_addr.load()),  # From depostior
        Assert(
            Or(
                And(
                    Gtxn[1].type_enum() == Int(1),  # ALGO payment
                    Gtxn[1].amount() == d_dep_amt.load(),  # Amount matches
                ),
                And(
                    Gtxn[1].type_enum() == Int(4),  # ASA transfer
                    Gtxn[1].xfer_asset() == d_dep_asset.load(),  # ASA ID matches
                    Gtxn[1].asset_amount() == d_dep_amt.load(),  # Amount matches
                ),
            )
        ),
        # Checking the depositor's collateral vs Gtxn[2]
        Assert(Gtxn[2].sender() == d_addr.load()),  # From depostior
        Assert(
            Or(
                And(
                    Gtxn[2].type_enum() == Int(1),  # ALGO payment
                    Gtxn[2].amount() == d_col_amt.load(),  # Amount matches
                ),
                And(
                    Gtxn[2].type_enum() == Int(4),  # ASA transfer
                    Gtxn[2].xfer_asset() == d_col_asset.load(),  # ASA ID matches
                    Gtxn[2].asset_amount() == d_col_amt.load(),  # Amount matches
                ),
            )
        ),
        # Now need to branch to check if the other side has alleged already
        # First check if the other side is even opted into the app
        If(App.optedIn(Txn.accounts[1], Global.current_application_id()) == Int(0))
        # If not, go ahead and create the deposit as there is nothing to check yet
        .Then(create_pending_deposit())
        # If so
        .ElseIf(App.optedIn(Txn.accounts[1], Global.current_application_id()) == Int(1))
        .Then(
            Seq(
                # Get the MaybeValue from app.localGetEx
                b_app_status,
                # Then check the value of the MaybeValue
                If(b_app_status.value() == Int(4))
                .Then(create_pending_deposit())
                .ElseIf(b_app_status.value() == Int(1))
                .Then(Seq(check_deposit_details(), lock_in_deposit())),
            )
        )
        .Else(
            # In any other scenario, reject the atomic group
            Reject()
        ),
        # Opt into any ASAs in the assets array
        For(
            i.store(Int(0)), i.load() < Txn.assets.length(), i.store(i.load() + Int(1))
        ).Do(opt_into_asa(Txn.assets[i.load()])),
        # Approve the deposit atomic group
        Approve(),
    )

    # If status is:
    # 1 - Allow disbursement after matching deposit data of sender
    # 2 - Set payout amounts in state and set status to 3
    # 3 - Check payout amounts and complete disbursement, then set status to 4
    on_disburse = Seq(
        Assert(App.globalGet(Bytes("app_status")) == Int(1)),
        check_accounts(),
        d_addr.store(Txn.accounts[0]),
        b_addr.store(Txn.accounts[1]),
        # Store the four app args
        return_to_you_amt.store(Btoi(Txn.application_args[1])),
        send_to_them_amt.store(Btoi(Txn.application_args[2])),
        you_receive_amt.store(Btoi(Txn.application_args[3])),
        return_to_them_amt.store(Btoi(Txn.application_args[4])),
        # Get deposit details out of local state
        d_dep_asset.store(App.localGet(d_addr.load(), Bytes("yourDepositAsset"))),
        d_dep_amt.store(App.localGet(d_addr.load(), Bytes("yourDepositAmount"))),
        d_col_asset.store(App.localGet(d_addr.load(), Bytes("yourCollateralAsset"))),
        d_col_amt.store(App.localGet(d_addr.load(), Bytes("yourCollateralAmount"))),
        b_dep_asset.store(App.localGet(d_addr.load(), Bytes("theirDepositAsset"))),
        b_dep_amt.store(App.localGet(d_addr.load(), Bytes("theirDepositAmount"))),
        b_col_asset.store(App.localGet(d_addr.load(), Bytes("theirCollateralAsset"))),
        b_col_amt.store(App.localGet(d_addr.load(), Bytes("theirCollateralAmount"))),
        # Checks your own status only; the counterparty could have cleared state
        # 1 - Allow disbursement after matching deposit data of sender
        If(App.localGet(d_addr.load(), Bytes("status")) == Int(1)).Then(
            # Check that the disbursement matches the data and goes back to sender (nowhere else)
            Seq(
                Assert(
                    return_to_you_amt.load()
                    == App.localGet(d_addr.load(), Bytes("yourDepositAmount"))
                ),
                Assert(send_to_them_amt.load() == Int(0)),
                Assert(you_receive_amt.load() == Int(0)),
                Assert(return_to_them_amt.load() == Int(0)),
                # Set status back to 4 to be ready for the next deposit
                App.localPut(d_addr.load(), Bytes("status"), Int(4)),
                If(return_to_you_amt.load() > Int(0)).Then(
                    send_algo_or_asa(
                        d_dep_asset.load(),
                        d_dep_amt.load(),
                        d_addr.load(),
                    )
                ),
                If(d_col_amt.load() > Int(0)).Then(
                    send_algo_or_asa(
                        d_col_asset.load(), d_col_amt.load(), d_addr.load()
                    )
                ),
                # Clear local state except for status to be ready for the next deal
                App.localDel(d_addr.load(), Bytes("theirAddress")),
                App.localDel(d_addr.load(), Bytes("yourDepositAsset")),
                App.localDel(d_addr.load(), Bytes("yourDepositAmount")),
                App.localDel(d_addr.load(), Bytes("yourCollateralAsset")),
                App.localDel(d_addr.load(), Bytes("yourCollateralAmount")),
                App.localDel(d_addr.load(), Bytes("theirDepositAsset")),
                App.localDel(d_addr.load(), Bytes("theirDepositAmount")),
                App.localDel(d_addr.load(), Bytes("theirCollateralAsset")),
                App.localDel(d_addr.load(), Bytes("theirCollateralAmount")),
                App.localDel(d_addr.load(), Bytes("returnToYouAmount")),
                App.localDel(d_addr.load(), Bytes("sendToThemAmount")),
                App.localDel(d_addr.load(), Bytes("youReceiveAmount")),
                App.localDel(d_addr.load(), Bytes("returnToThemAmount")),
                App.localDel(d_addr.load(), Bytes("note")),
            )
        )
        # 2 - If funds are locked in, check disbursement request & check counterparty state
        ### You can be status 2 or 3
        ### If they are 2, just write over yours
        ### If they are status 3, check for match
        ###     If match, disburse
        ###     If no match, update your data and return a message saying mismatch
        .ElseIf(
            Or(
                App.localGet(d_addr.load(), Bytes("status")) == Int(2),
                App.localGet(d_addr.load(), Bytes("status")) == Int(3),
            )
        ).Then(
            Seq(
                # Check that the disbursement matches the data and set status to 3 for pending disbursement
                # Check data and if all good then send out the deposits & colalteral
                # Check that the two accounts provided have identical escrow data
                # Check that each account's data is pointing to the other
                Assert(
                    App.localGet(d_addr.load(), Bytes("theirAddress")) == b_addr.load()
                ),
                Assert(
                    App.localGet(b_addr.load(), Bytes("theirAddress")) == d_addr.load()
                ),
                # Note that the roles are flipped depending on the account's perspective
                Assert(
                    App.localGet(d_addr.load(), Bytes("yourDepositAsset"))
                    == App.localGet(b_addr.load(), Bytes("theirDepositAsset"))
                ),
                Assert(
                    App.localGet(d_addr.load(), Bytes("yourDepositAmount"))
                    == App.localGet(b_addr.load(), Bytes("theirDepositAmount"))
                ),
                Assert(
                    App.localGet(d_addr.load(), Bytes("yourCollateralAsset"))
                    == App.localGet(b_addr.load(), Bytes("theirCollateralAsset"))
                ),
                Assert(
                    App.localGet(d_addr.load(), Bytes("yourCollateralAmount"))
                    == App.localGet(b_addr.load(), Bytes("theirCollateralAmount"))
                ),
                Assert(
                    App.localGet(d_addr.load(), Bytes("theirDepositAsset"))
                    == App.localGet(b_addr.load(), Bytes("yourDepositAsset"))
                ),
                Assert(
                    App.localGet(d_addr.load(), Bytes("theirDepositAmount"))
                    == App.localGet(b_addr.load(), Bytes("yourDepositAmount"))
                ),
                Assert(
                    App.localGet(d_addr.load(), Bytes("theirCollateralAsset"))
                    == App.localGet(b_addr.load(), Bytes("yourCollateralAsset"))
                ),
                Assert(
                    App.localGet(d_addr.load(), Bytes("theirCollateralAmount"))
                    == App.localGet(b_addr.load(), Bytes("yourCollateralAmount"))
                ),
                Assert(
                    d_dep_amt.load()
                    == (return_to_you_amt.load() + send_to_them_amt.load())
                ),
                Assert(
                    b_dep_amt.load()
                    == (you_receive_amt.load() + return_to_them_amt.load())
                ),
                App.localPut(
                    d_addr.load(), Bytes("returnToYouAmount"), return_to_you_amt.load()
                ),
                App.localPut(
                    d_addr.load(), Bytes("sendToThemAmount"), send_to_them_amt.load()
                ),
                App.localPut(
                    d_addr.load(), Bytes("youReceiveAmount"), you_receive_amt.load()
                ),
                App.localPut(
                    d_addr.load(),
                    Bytes("returnToThemAmount"),
                    return_to_them_amt.load(),
                ),
                App.localPut(d_addr.load(), Bytes("status"), Int(3)),
                # If their state is 2
                If(App.localGet(b_addr.load(), Bytes("status")) == Int(2)).Then(
                    # Write disbursement data to depositor state and update status to 3
                    Seq(
                        Log(Bytes("Payout pending confirmation")),
                    )
                )
                # If their state is 3 and the disbursement details match (note the directions)
                .ElseIf(
                    And(
                        App.localGet(b_addr.load(), Bytes("status")) == Int(3),
                        return_to_you_amt.load()
                        == App.localGet(b_addr.load(), Bytes("returnToThemAmount")),
                        send_to_them_amt.load()
                        == App.localGet(b_addr.load(), Bytes("youReceiveAmount")),
                        you_receive_amt.load()
                        == App.localGet(b_addr.load(), Bytes("sendToThemAmount")),
                        return_to_them_amt.load()
                        == App.localGet(b_addr.load(), Bytes("returnToYouAmount")),
                    )
                )
                .Then(
                    Seq(
                        # Check that the disbursement matches the deposit data
                        # and then set status to 4 & generate payments
                        # Transform the payment instructions into disbursements
                        If(return_to_you_amt.load() > Int(0)).Then(
                            send_algo_or_asa(
                                d_dep_asset.load(),
                                return_to_you_amt.load(),
                                d_addr.load(),
                            )
                        ),
                        If(send_to_them_amt.load() > Int(0)).Then(
                            send_algo_or_asa(
                                d_dep_asset.load(),
                                send_to_them_amt.load(),
                                b_addr.load(),
                            )
                        ),
                        If(you_receive_amt.load() > Int(0)).Then(
                            send_algo_or_asa(
                                b_dep_asset.load(),
                                you_receive_amt.load(),
                                d_addr.load(),
                            )
                        ),
                        If(return_to_them_amt.load() > Int(0)).Then(
                            send_algo_or_asa(
                                b_dep_asset.load(),
                                return_to_them_amt.load(),
                                b_addr.load(),
                            )
                        ),
                        # Return depositor and beneficiary collateral
                        If(d_col_amt.load() > Int(0)).Then(
                            send_algo_or_asa(
                                d_col_asset.load(), d_col_amt.load(), d_addr.load()
                            )
                        ),
                        If(b_col_amt.load() > Int(0)).Then(
                            send_algo_or_asa(
                                b_col_asset.load(), b_col_amt.load(), b_addr.load()
                            )
                        ),
                        # Reset local state from both accounts to ready status 4
                        # Depositor side
                        # Set status
                        App.localPut(d_addr.load(), Bytes("status"), Int(4)),
                        # Delete all other local state
                        App.localDel(d_addr.load(), Bytes("theirAddress")),
                        App.localDel(d_addr.load(), Bytes("yourDepositAsset")),
                        App.localDel(d_addr.load(), Bytes("yourDepositAmount")),
                        App.localDel(d_addr.load(), Bytes("yourCollateralAsset")),
                        App.localDel(d_addr.load(), Bytes("yourCollateralAmount")),
                        App.localDel(d_addr.load(), Bytes("theirDepositAsset")),
                        App.localDel(d_addr.load(), Bytes("theirDepositAmount")),
                        App.localDel(d_addr.load(), Bytes("theirCollateralAsset")),
                        App.localDel(d_addr.load(), Bytes("theirCollateralAmount")),
                        App.localDel(d_addr.load(), Bytes("returnToYouAmount")),
                        App.localDel(d_addr.load(), Bytes("sendToThemAmount")),
                        App.localDel(d_addr.load(), Bytes("youReceiveAmount")),
                        App.localDel(d_addr.load(), Bytes("returnToThemAmount")),
                        App.localDel(d_addr.load(), Bytes("note")),
                        # Beneficiary side
                        # Set status
                        App.localPut(b_addr.load(), Bytes("status"), Int(4)),
                        # Delete all other local state
                        App.localDel(b_addr.load(), Bytes("theirAddress")),
                        App.localDel(b_addr.load(), Bytes("yourDepositAsset")),
                        App.localDel(b_addr.load(), Bytes("yourDepositAmount")),
                        App.localDel(b_addr.load(), Bytes("yourCollateralAsset")),
                        App.localDel(b_addr.load(), Bytes("yourCollateralAmount")),
                        App.localDel(b_addr.load(), Bytes("theirDepositAsset")),
                        App.localDel(b_addr.load(), Bytes("theirDepositAmount")),
                        App.localDel(b_addr.load(), Bytes("theirCollateralAsset")),
                        App.localDel(b_addr.load(), Bytes("theirCollateralAmount")),
                        App.localDel(b_addr.load(), Bytes("returnToYouAmount")),
                        App.localDel(b_addr.load(), Bytes("sendToThemAmount")),
                        App.localDel(b_addr.load(), Bytes("youReceiveAmount")),
                        App.localDel(b_addr.load(), Bytes("returnToThemAmount")),
                        App.localDel(b_addr.load(), Bytes("note")),
                        Log(Bytes("Payout complete")),
                    )
                )
                .Else(Log(Bytes("Payout terms mismatch"))),
            )
        )
        # If anything else sketchy was submitted, reject
        .Else(Reject()),
        Approve(),
    )

    on_change_fee = Seq(
        Assert(Txn.sender() == Global.creator_address()),
        App.globalPut(Bytes("base_fee"), Btoi(Txn.application_args[1])),
        Log(
            Concat(
                Bytes("Base fee "),
                Itob(App.globalGet(Bytes("base_fee"))),
            )
        ),
        Approve(),
    )

    on_change_app_status = Seq(
        Assert(Txn.sender() == Global.creator_address()),
        App.globalPut(Bytes("app_status"), Btoi(Txn.application_args[1])),
        Log(
            Concat(
                Bytes("App status "),
                Itob(App.globalGet(Bytes("app_status"))),
            )
        ),
        Approve(),
    )

    on_optin = Seq(
        If(App.localGet(Txn.accounts[0], Bytes("status")) == Int(0))
        .Then(App.localPut(Txn.accounts[0], Bytes("status"), Int(4)))
        .Else(Reject()),
        Approve(),
    )

    on_closeout = Seq(
        # Only if the sending account is in status 4 for no active deal, approve
        # This protects the user from closing out if it would strand a deposit
        If(App.localGet(Txn.accounts[0], Bytes("status")) == Int(4))
        .Then(Approve())
        .Else(Reject())
    )

    on_update = Seq(Assert(Txn.sender() == Global.creator_address()), Approve())

    on_delete = Seq(Assert(Txn.sender() == Global.creator_address()), Approve())

    # Provides the ways to call the app: set it up, make a deposit, or request disbursement
    on_call_method = Txn.application_args[0]
    on_call = Cond(
        [on_call_method == Bytes("deposit"), on_deposit],
        [on_call_method == Bytes("disburse"), on_disburse],
        [on_call_method == Bytes("change_fee"), on_change_fee],
        [on_call_method == Bytes("change_app_status"), on_change_app_status],
    )

    program = Seq(
        Assert(
            And(
                Txn.rekey_to() == Global.zero_address(),
                Txn.close_remainder_to() == Global.zero_address(),
                Txn.asset_close_to() == Global.zero_address(),
            ),
        ),
        Cond(
            [Txn.application_id() == Int(0), on_create],
            [Txn.on_completion() == OnComplete.NoOp, on_call],
            [Txn.on_completion() == OnComplete.OptIn, on_optin],
            [Txn.on_completion() == OnComplete.CloseOut, on_closeout],
            [Txn.on_completion() == OnComplete.UpdateApplication, on_update],
            [Txn.on_completion() == OnComplete.DeleteApplication, on_delete],
        ),
    )
    return program


def clear_state_program():
    """The application's logic for clear state calls"""
    return Approve()


if __name__ == "__main__":
    with open("alright_approval.teal", "w") as f:
        approval_compiled = compileTeal(
            approval_program(), mode=Mode.Application, version=6
        )
        f.write(approval_compiled)

    with open("alright_clear_state.teal", "w") as f:
        clear_state_compiled = compileTeal(
            clear_state_program(), mode=Mode.Application, version=6
        )
        f.write(clear_state_compiled)
