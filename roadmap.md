# Cold Storage Solution - Phase 1 Checklist (Aligned to Screenshot)

This checklist is updated to match the latest backend implementation and the screenshot scope.

## 1. Inward Management

- [x] Entry of incoming stock
- [x] SKU generation
- [x] Quantity, weight, and item metadata capture

## 2. Storage Zone Allocation & Capacity Management

- [ ] Definition of storage zones (rack, chamber, floor, temperature zone)
	- Implemented: `rack`, `room`, `temperature_zone`
	- Pending: explicit `chamber` and `floor` entities
- [ ] Capacity configuration per zone
	- Implemented: rack-level capacity
	- Pending: chamber/floor/temperature-zone-level capacity controls
- [ ] System-based allocation during inward
	- Pending: inward currently requires operator-selected `rack_id`

## 3. Inventory Tracking & Aging

- [ ] Real-time inventory visibility
	- Partial: inventory/product listing endpoints exist, but no dedicated real-time dashboard view
- [ ] Batch-wise and SKU-wise stock tracking
	- Partial: SKU and lot/batch are captured in product + ledger flow; dedicated batch/SKU analytics views are pending
- [ ] Aging calculation based on inward date
	- Pending: explicit aging field/bucket response not yet exposed in inventory APIs

## 4. Basic User Roles

- [x] Admin
- [x] Warehouse / Store Operator
