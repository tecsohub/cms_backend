# **Cold Storage Solution \- Phase 1 Implementation Checklist**

This checklist outlines all required features and tasks for **Phase 1** of the Cold Storage implementation, derived from the functional requirements and wireframe notes.

## **1\. Inward Management (Truck-Based)**

* \[ \] **Truck-Level Entry:** Implement inward entry form allowing one inward record per arriving truck.
* \[ \] **Metadata Capture:** Form fields to capture Client, Truck Number, Arrival Date & Time.
* \[ \] **Optional Fields:** Form fields for Driver Details and Remarks.
* \[ \] **Multi-Pallet Support:** UI to add multiple items and pallets under a single inward truck record.
* \[ \] **Auto-Generation:** System auto-generates a unique Inward Reference Number.
* \[ \] **Status Tracking:** Implement inward status lifecycle (Draft \-\> Pallets Created \-\> Allocated \-\> Completed).
* \[ \] **Validation Constraint:** Prevent inward record closure/completion until *all* associated pallets are allocated to a zone.
* \[ \] **Audit Trail:** Auto-timestamp all inward creation and status change activities.

## **2\. Pallet & SKU Management (Atomic Unit)**

* \[ \] **Data Capture:** Form to capture pallet-level data (Item, Quantity/Weight, UOM, Batch/Lot Number, Inward Date/Harvest Date).
* \[ \] **SKU Generation:** Auto-generate a unique SKU per physical pallet upon saving.
* \[ \] **SKU Structure:** Format SKU based on rules (e.g., Client \+ Item \+ Pallet Reference).
* \[ \] **Immutability Rules:** Lock pallet quantity and prevent manual editing of the SKU once generated.
* \[ \] **Pallet Status:** Track individual pallet status (Pending Allocation, Stored, Moved).

## **3\. Storage Zone & Capacity Management**

* \[x\] **Zone Definition:** UI for Admin to define storage zones hierarchy (Chambers, Racks, Floors, Temp Zones).
* \[ \] **Zone Parameters:** Configure Min/Max temperature ranges per zone.
* \[ \] **Capacity Configuration:** Configure maximum capacity per zone (by weight or pallet count).
* \[ \] **Zone Status:** Ability to mark zones as Active or Maintenance.

## **4\. Pallet Zone Allocation**

* \[ \] **System Suggestions:** Algorithm to suggest suitable storage zones based on temperature requirements and available capacity.
* \[x\] **Allocation Execution:** UI for Warehouse Operator to allocate pallets to specific zones.
* \[x\] **Capacity Validation:** Block allocation if the selected zone's capacity limit is exceeded.
* \[x\] **Real-time Updates:** Automatically update/reduce zone available capacity upon successful allocation.
* \[ \] **Inventory Activation:** Ensure pallet inventory becomes "active" only after confirmed allocation.
* \[x\] **Append-Only Records:** Ensure allocation records are immutable and appended to history.

## **5\. Inventory Tracking & Aging**

* \[ \] **Real-Time Visibility:** Dashboard/List view showing live, pallet-level inventory (read-only, derived from allocations).
* \[ \] **Data Display:** Show Pallet/SKU, Client, Item, Quantity, Zone, Inward Date, and Aging in days.
* \[ \] **Aging Calculation:** System automatically calculates age in days based on the inward date.
* \[ \] **Aging Buckets:** Classify inventory into configured buckets (e.g., \< 7 days, 8–15 days, \> 15 days).
* \[ \] **Visual Indicators:** Implement color-coded tags for stock health (Fresh \[Green\], Aging \[Yellow\], Critical \[Red\]).
* \[ \] **Search & Filter:** Implement filters by Client, Item, Storage Zone, and Aging Bucket. Enable direct search by SKU/Pallet Code.

## **6\. QR Code Generation & Scanning (Mobile Readiness)**

* \[ \] **Generation:** Automatically generate a QR code for every new pallet.
* \[ \] **QR Payload:** Link QR code to Pallet SKU, Pallet ID, and Client.
* \[ \] **Printable Labels:** UI to generate and print pallet labels containing the QR code.
* \[ \] **Scanning Support:** Allow mobile/handheld scanners to scan QR codes to instantly open pallet details or verify zone placement.

## **7\. Pallet Movement (Internal Transfers)**

* \[ \] **Movement UI:** Screen to select an allocated pallet and move it to a new storage zone.
* \[ \] **Reason Capture:** Mandatory text field/dropdown to capture the reason for movement.
* \[ \] **Validation:** Re-validate temperature compatibility and target zone capacity before confirming movement.
* \[ \] **Data Integrity:** Ensure movement updates location but does *not* alter inventory quantity or billing start dates.
* \[ \] **Movement History:** Maintain a complete, user-stamped, and time-stamped log of all internal movements.

## **8\. Billing Preview (Derived View \- Phase 1\)**

* \[ \] **Draft Calculation:** Calculate billable amount based on Pallet Quantity × Billable Days × Rate.
* \[ \] **Preview UI:** Display a read-only, client-wise billing preview showing pallet-level charge breakdowns.

## **9\. Basic User & Role Management**

* \[x\] **Role Setup:** Implement Admin role (full config/governance access).
* \[x\] **Role Setup:** Implement Warehouse / Store Operator role (mobile/web inward & allocation execution).
* \[x\] *(Note: Ensure framework supports extending to other roles like Billing, Client Viewer later).*
* \[ \] **User Management UI:** Admin screen to Add/Edit users, assign roles, and toggle Status (Active/Inactive).
* \[x\] **Access Control:** Prevent inactive users from logging in; restrict views based on assigned role.

## **10\. Audit Logs & Traceability (Critical)**

* \[x\] **Immutable Logging:** Implement background logging for Inward creation, Pallet creation, Zone Allocation, and Movements.
* \[x\] **Log Details:** Capture exactly *Who* (User ID), *When* (Timestamp), and *What* (Before/After state where applicable).
* \[ \] **Audit Views:** Provide read-only audit trail screens for admins.

## **11\. Dashboards & Reports**

* \[ \] **Operational Dashboard:** Display widgets for Total Pallets in Storage, Zone Capacity Utilization, Pending Allocations, and Aging Distribution.
* \[ \] **Basic Reports:** Generate Inward Summary, Inventory Aging, Zone Utilization, and Movement History reports.

**Out of Scope for Phase 1 (Do Not Implement Yet):**

* Outward / Dispatch workflows
* Waste and disposal management workflows
* Automated / Final Invoicing and accounting generation
* Client self-service portals
* IoT Sensor Integrations
