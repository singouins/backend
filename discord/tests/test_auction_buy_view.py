# -*- coding: utf8 -*-

import uuid
from unittest.mock import MagicMock, patch

import pytest

from mongo.models.Auction import AuctionDocument
from mongo.models.Highscore import HighscoreDocument
from mongo.models.Item import ItemDocument
from mongo.models.Satchel import SatchelDocument
from subcommands.auction._view import buyView


@pytest.fixture
def redis_stub():
    # buyView's success path publishes an optional "someone bought your
    # item" DM notification over Redis pub/sub - a side effect unrelated
    # to what these tests assert, and this suite deliberately runs
    # without a live Redis (see scripts/test-local.sh).
    stub = MagicMock()
    with patch('subcommands.auction._view.r', stub):
        yield stub


async def _setup_trade(make_creature, make_satchel, make_highscore, make_item, make_auction, *, buyer_banana=100, price=20):  # noqa: E501
    seller = make_creature(name='Seller')
    buyer = make_creature(name='Buyer')
    seller_satchel = make_satchel(_id=seller.id, currency={'banana': 0})
    buyer_satchel = make_satchel(_id=buyer.id, currency={'banana': buyer_banana})
    seller_highscore = make_highscore(_id=seller.id)
    buyer_highscore = make_highscore(_id=buyer.id)
    item = make_item(bearer=seller.id, metatype='armor', metaid=1, auctioned=True)
    auction = make_auction(
        item={'id': item.id, 'metaid': 1, 'metatype': 'armor', 'name': 'Test Armor', 'rarity': 'Common'},  # noqa: E501
        price=price,
        seller={'id': seller.id, 'name': seller.name},
        )
    return dict(
        seller=seller, buyer=buyer,
        seller_satchel=seller_satchel, buyer_satchel=buyer_satchel,
        seller_highscore=seller_highscore, buyer_highscore=buyer_highscore,
        item=item, auction=auction,
        )


async def test_buy_success_transfers_currency_and_item(bot, make_ctx, make_interaction, get_callback, make_creature, make_satchel, make_highscore, make_item, make_auction, redis_stub):  # noqa: E501
    state = await _setup_trade(make_creature, make_satchel, make_highscore, make_item, make_auction)  # noqa: E501

    ctx = make_ctx()
    view = buyView(ctx, str(state['buyer'].id), str(state['auction'].id))
    interaction = make_interaction(user=ctx.author)

    await view.ok_button_callback.callback(interaction)

    assert interaction.response.edit_message.call_count == 1
    assert AuctionDocument.objects(_id=state['auction'].id).count() == 0

    state['buyer_satchel'].reload()
    state['seller_satchel'].reload()
    assert state['buyer_satchel'].currency.banana == 80
    assert state['seller_satchel'].currency.banana == 20

    state['item'].reload()
    assert state['item'].auctioned is False
    assert state['item'].bearer == state['buyer'].id


async def test_buy_success_highscore_bug_credits_seller_for_both(bot, make_ctx, make_interaction, get_callback, make_creature, make_satchel, make_highscore, make_item, make_auction, redis_stub):  # noqa: E501
    # Documents a real gap: HighscoreBuyer is queried by Auction.seller.id
    # instead of self.buyeruuid (subcommands/auction/_view.py), so it's
    # literally the same document as HighscoreSeller. Both the 'sold' and
    # 'bought' increments land on the seller's Highscore, and the buyer's
    # own Highscore is never touched.
    state = await _setup_trade(make_creature, make_satchel, make_highscore, make_item, make_auction)  # noqa: E501

    ctx = make_ctx()
    view = buyView(ctx, str(state['buyer'].id), str(state['auction'].id))
    interaction = make_interaction(user=ctx.author)

    await view.ok_button_callback.callback(interaction)

    state['seller_highscore'].reload()
    state['buyer_highscore'].reload()
    assert state['seller_highscore'].internal.item.sold == 1
    assert state['seller_highscore'].internal.item.bought == 1  # should be on the buyer instead
    assert state['buyer_highscore'].internal.item.bought == 0  # never credited


async def test_buy_insufficient_balance_is_rejected(bot, make_ctx, make_interaction, get_callback, make_creature, make_satchel, make_highscore, make_item, make_auction, redis_stub):  # noqa: E501
    state = await _setup_trade(make_creature, make_satchel, make_highscore, make_item, make_auction, buyer_banana=0, price=20)  # noqa: E501

    ctx = make_ctx()
    view = buyView(ctx, str(state['buyer'].id), str(state['auction'].id))
    interaction = make_interaction(user=ctx.author)

    await view.ok_button_callback.callback(interaction)

    assert interaction.response.edit_message.call_count == 1
    assert AuctionDocument.objects(_id=state['auction'].id).count() == 1
    state['buyer_satchel'].reload()
    assert state['buyer_satchel'].currency.banana == 0


async def test_buy_unknown_auction_responds_once(bot, make_ctx, make_interaction, redis_stub):
    ctx = make_ctx()
    view = buyView(ctx, str(uuid.uuid4()), str(uuid.uuid4()))
    interaction = make_interaction(user=ctx.author)

    await view.ok_button_callback.callback(interaction)

    assert interaction.response.edit_message.call_count == 1


async def test_buy_missing_highscore_raises_attributeerror(bot, make_ctx, make_interaction, make_creature, make_satchel, make_item, make_auction, redis_stub):  # noqa: E501
    # Documents a real gap: the HighscoreDocument.DoesNotExist handler
    # calls interaction.response.respond(...), which isn't a real method
    # on InteractionResponse (send_message/edit_message/defer are) - so
    # this branch crashes instead of showing the intended error message.
    seller = make_creature(name='Seller')
    buyer = make_creature(name='Buyer')
    make_satchel(_id=seller.id, currency={'banana': 0})
    make_satchel(_id=buyer.id, currency={'banana': 100})
    item = make_item(bearer=seller.id, metatype='armor', metaid=1, auctioned=True)
    auction = make_auction(
        item={'id': item.id, 'metaid': 1, 'metatype': 'armor', 'name': 'Test Armor', 'rarity': 'Common'},  # noqa: E501
        price=20,
        seller={'id': seller.id, 'name': seller.name},
        )
    # Deliberately no Highscore documents for either creature.
    assert HighscoreDocument.objects.count() == 0

    ctx = make_ctx()
    view = buyView(ctx, str(buyer.id), str(auction.id))
    interaction = make_interaction(user=ctx.author)

    with pytest.raises(AttributeError):
        await view.ok_button_callback.callback(interaction)


async def test_ko_button_cancels_without_side_effects(bot, make_ctx, make_interaction, make_creature, make_satchel, make_highscore, make_item, make_auction, redis_stub):  # noqa: E501
    state = await _setup_trade(make_creature, make_satchel, make_highscore, make_item, make_auction)  # noqa: E501

    ctx = make_ctx()
    view = buyView(ctx, str(state['buyer'].id), str(state['auction'].id))
    interaction = make_interaction(user=ctx.author)

    await view.ko_button_callback.callback(interaction)

    assert interaction.response.edit_message.call_count == 1
    assert AuctionDocument.objects(_id=state['auction'].id).count() == 1
    assert ItemDocument.objects(_id=state['item'].id).first().auctioned is True
    assert SatchelDocument.objects(_id=state['buyer'].id).first().currency.banana == 100


async def test_interaction_check_blocks_other_users(bot, make_ctx, make_interaction):
    ctx = make_ctx(author_name='the_buyer')
    view = buyView(ctx, str(uuid.uuid4()), str(uuid.uuid4()))
    other_user_interaction = make_interaction(user=MagicMock(name='someone_else'))

    allowed = await view.interaction_check(other_user_interaction)

    assert allowed is False
    assert other_user_interaction.response.send_message.call_count == 1


async def test_interaction_check_allows_the_original_author(bot, make_ctx, make_interaction):
    ctx = make_ctx(author_name='the_buyer')
    view = buyView(ctx, str(uuid.uuid4()), str(uuid.uuid4()))
    own_interaction = make_interaction(user=ctx.author)

    allowed = await view.interaction_check(own_interaction)

    assert allowed is True
    assert own_interaction.response.send_message.call_count == 0
