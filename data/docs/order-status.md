# Order Status Definitions

## Statuses

- `pending`: the order has been placed but not yet shipped.
- `shipped`: the order has left the warehouse and is in transit. It has a ship date but no delivery date.
- `delivered`: the order has arrived. It has both a ship date and a delivery date.
- `cancelled`: the order was cancelled before shipping. It has no ship or delivery date, and no payment was captured.

## Order totals

The order total is the sum of quantity times unit price over all items. Shipping is free, so it is not part of the total.
