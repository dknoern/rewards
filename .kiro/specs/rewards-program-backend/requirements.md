# Requirements Document

## Introduction

This document specifies the requirements for a casual dining rewards program backend system that manages member enrollment, star accrual from purchases, star redemptions, and tier-based benefits. The system processes event-based messages for rewards activities and maintains member balances and tier status across three membership tiers (Green, Gold, Reserve).

## Glossary

- **Rewards_System**: The backend system that processes rewards program events and maintains member data
- **Member**: A registered participant in the rewards program with a unique membership ID
- **Star**: The currency unit earned through purchases and redeemed for products
- **Tier**: Membership level (Green, Gold, or Reserve) based on annual star accumulation
- **Qualifying_Activity**: A purchase transaction that counts toward preventing star expiration
- **Annual_Star_Count**: Total stars earned by a member within the current 12-month tier evaluation period
- **Star_Balance**: Current number of unredeemed stars available to a member
- **Double_Star_Day**: A promotional day when members earn twice the normal star rate
- **Event_Message**: An inbound message specifying a rewards activity (signup, purchase, redemption)
- **Membership_ID**: Unique identifier assigned to each member upon enrollment

## Requirements

### Requirement 1: Member Enrollment

**User Story:** As a customer, I want to sign up for rewards membership, so that I can start earning and redeeming stars.

#### Acceptance Criteria

1. WHEN a valid signup Event_Message is received, THE Rewards_System SHALL create a new Member with a unique Membership_ID
2. WHEN a Member is created, THE Rewards_System SHALL initialize the Member with Green Tier status
3. WHEN a Member is created, THE Rewards_System SHALL initialize the Star_Balance to zero
4. WHEN a Member is created, THE Rewards_System SHALL record the enrollment timestamp
5. WHEN a signup Event_Message with an existing Membership_ID is received, THE Rewards_System SHALL return an error indicating duplicate enrollment

### Requirement 2: Purchase Event Processing

**User Story:** As a member, I want my purchases to be logged and earn stars, so that I can accumulate rewards.

#### Acceptance Criteria

1. WHEN a valid purchase Event_Message is received, THE Rewards_System SHALL validate the Membership_ID exists
2. WHEN a purchase Event_Message contains an invalid Membership_ID, THE Rewards_System SHALL return an error indicating member not found
3. WHEN a valid purchase Event_Message is received, THE Rewards_System SHALL record the purchase transaction with timestamp and amount
4. WHEN a valid purchase Event_Message is received, THE Rewards_System SHALL calculate stars based on the Member's current Tier and purchase amount
5. WHEN a valid purchase Event_Message is received, THE Rewards_System SHALL add the calculated stars to the Member's Star_Balance
6. WHEN a valid purchase Event_Message is received, THE Rewards_System SHALL update the Member's last Qualifying_Activity timestamp

### Requirement 3: Star Accrual Rates by Tier

**User Story:** As a member, I want to earn stars at a rate appropriate to my tier, so that I receive the correct rewards for my loyalty level.

#### Acceptance Criteria

1. WHILE a Member has Green Tier status, THE Rewards_System SHALL calculate stars at 1.0 stars per dollar spent
2. WHILE a Member has Gold Tier status, THE Rewards_System SHALL calculate stars at 1.2 stars per dollar spent
3. WHILE a Member has Reserve Tier status, THE Rewards_System SHALL calculate stars at 1.7 stars per dollar spent
4. WHERE a purchase occurs on a Double_Star_Day, THE Rewards_System SHALL multiply the calculated stars by 2.0
5. WHERE a purchase includes personal cup usage, THE Rewards_System SHALL multiply the calculated stars by 2.0

### Requirement 4: Redemption Processing

**User Story:** As a member, I want to redeem my stars for products, so that I can receive free items.

#### Acceptance Criteria

1. WHEN a valid redemption Event_Message is received, THE Rewards_System SHALL validate the Membership_ID exists
2. WHEN a redemption Event_Message is received, THE Rewards_System SHALL validate the Member's Star_Balance is sufficient for the requested redemption
3. WHEN a Member's Star_Balance is insufficient for redemption, THE Rewards_System SHALL return an error indicating insufficient stars
4. WHEN a valid redemption Event_Message is received with sufficient stars, THE Rewards_System SHALL deduct the specified stars from the Member's Star_Balance
5. WHEN a valid redemption Event_Message is received with sufficient stars, THE Rewards_System SHALL record the redemption transaction with timestamp and star amount
6. THE Rewards_System SHALL support redemptions starting at 60 stars

### Requirement 5: Tier Evaluation and Promotion

**User Story:** As a member, I want my tier status to be automatically updated based on my annual star earnings, so that I receive appropriate benefits.

#### Acceptance Criteria

1. WHEN a Member's Annual_Star_Count reaches 500 stars, THE Rewards_System SHALL promote the Member to Gold Tier
2. WHEN a Member's Annual_Star_Count reaches 2500 stars, THE Rewards_System SHALL promote the Member to Reserve Tier
3. WHEN a Member is promoted to a new Tier, THE Rewards_System SHALL record the tier change timestamp
4. WHEN a Member is promoted to a new Tier, THE Rewards_System SHALL maintain the tier status for 12 months from the promotion date
5. WHEN a 12-month tier evaluation period ends, THE Rewards_System SHALL recalculate the Member's Tier based on stars earned in the past 12 months

### Requirement 6: Star Expiration for Green Members

**User Story:** As a Green tier member, I want my stars to remain active when I make monthly purchases, so that I don't lose my earned rewards.

#### Acceptance Criteria

1. WHILE a Member has Green Tier status, THE Rewards_System SHALL track the age of each star from its earning date
2. WHILE a Member has Green Tier status, THE Rewards_System SHALL expire stars that are older than 6 months without monthly Qualifying_Activity
3. WHEN a Green Tier Member completes a Qualifying_Activity, THE Rewards_System SHALL reset the expiration timer for all active stars
4. WHEN stars expire for a Green Tier Member, THE Rewards_System SHALL deduct the expired stars from the Member's Star_Balance
5. WHEN stars expire for a Green Tier Member, THE Rewards_System SHALL record the expiration event with timestamp and star count

### Requirement 7: Non-Expiring Stars for Gold and Reserve Members

**User Story:** As a Gold or Reserve member, I want my stars to never expire, so that I can accumulate rewards without time pressure.

#### Acceptance Criteria

1. WHILE a Member has Gold Tier status, THE Rewards_System SHALL maintain all earned stars without expiration
2. WHILE a Member has Reserve Tier status, THE Rewards_System SHALL maintain all earned stars without expiration
3. WHEN a Member is promoted from Green to Gold Tier, THE Rewards_System SHALL remove expiration dates from all existing stars

### Requirement 8: Member Balance and Status Query

**User Story:** As a system integrator, I want to query a member's current star balance and tier status, so that I can display this information to the member.

#### Acceptance Criteria

1. WHEN a valid query request with Membership_ID is received, THE Rewards_System SHALL return the Member's current Star_Balance
2. WHEN a valid query request with Membership_ID is received, THE Rewards_System SHALL return the Member's current Tier status
3. WHEN a valid query request with Membership_ID is received, THE Rewards_System SHALL return the Member's Annual_Star_Count
4. WHEN a query request with an invalid Membership_ID is received, THE Rewards_System SHALL return an error indicating member not found
5. WHEN a valid query request with Membership_ID is received, THE Rewards_System SHALL return the response within 200 milliseconds

### Requirement 9: Event Message Validation

**User Story:** As a system administrator, I want all inbound event messages to be validated, so that invalid data does not corrupt the system.

#### Acceptance Criteria

1. WHEN an Event_Message is received, THE Rewards_System SHALL validate the message contains all required fields
2. WHEN an Event_Message is missing required fields, THE Rewards_System SHALL return an error indicating which fields are missing
3. WHEN an Event_Message contains invalid data types, THE Rewards_System SHALL return an error indicating the validation failure
4. WHEN an Event_Message contains a negative purchase amount, THE Rewards_System SHALL return an error indicating invalid amount
5. WHEN an Event_Message contains a negative star redemption amount, THE Rewards_System SHALL return an error indicating invalid redemption

### Requirement 10: Idempotent Event Processing

**User Story:** As a system administrator, I want duplicate event messages to be handled safely, so that members are not credited or debited multiple times for the same transaction.

#### Acceptance Criteria

1. WHEN an Event_Message is received, THE Rewards_System SHALL check for a unique transaction identifier
2. WHEN an Event_Message with a duplicate transaction identifier is received, THE Rewards_System SHALL return the original transaction result without reprocessing
3. WHEN an Event_Message with a duplicate transaction identifier is received, THE Rewards_System SHALL not modify the Member's Star_Balance
4. THE Rewards_System SHALL maintain transaction identifiers for at least 30 days

### Requirement 11: Transaction History Audit Trail

**User Story:** As a member, I want a complete history of my rewards transactions, so that I can review my earning and redemption activity.

#### Acceptance Criteria

1. WHEN a purchase transaction is processed, THE Rewards_System SHALL record the transaction with timestamp, amount, and stars earned
2. WHEN a redemption transaction is processed, THE Rewards_System SHALL record the transaction with timestamp, stars redeemed, and item description
3. WHEN a tier change occurs, THE Rewards_System SHALL record the event with timestamp, previous tier, and new tier
4. WHEN stars expire, THE Rewards_System SHALL record the expiration event with timestamp and star count
5. WHEN a query for transaction history is received, THE Rewards_System SHALL return all transactions for the specified Membership_ID in chronological order

