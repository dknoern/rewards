I want to create backend code and infrastructure to support a casual dining rewards program that awards "stars" for purchase that can be redeemed for free product.

We need to design and build an event-based architecture that handles inbound messages that specify the following activities:
1. sign up for rewards membership, get a membership ID
2. log purchase, provide membership ID and receive stars (see rules below for accrual logic)
3. log redemptions, trade specified number of stars for product

The system needs to validate and handle inbound messages. Records of rewards activity for members will be maintained.  Members current star balance and membership tier will be tracked and available to query.

The following rules describe the "Rewards" loyalty program:

The Rewards program is structured into three tiers—**Green, Gold, and Reserve**—based on annual star accumulation, with stars redeemable for items starting at 60 stars. Members earn 1–1.7 stars per $1 spent, with higher tiers offering non-expiring stars and more "Double Star Days"

**Key Star Policy Details (2026 Reimagined Program):**

- **Tier Structure:**
    - **Green:** Entry level. Earn 1 star per $1 spent. Stars remain active with monthly qualifying activity.
    - **Gold (500+ stars/year):**
         Earn 1.2 stars per $1 spent. 
        **Stars never expire**
    - **Reserve (2,500+ stars/year):** Earn 1.7 stars per $1 spent. **Stars never expire**.
    
- **Star Expiration & Activity:** For Green members, stars expire after 6 months without qualifying monthly activity. Gold and Reserve members' stars do not expire.

- **Earning Stars:** Stars are earned by paying with the Starbucks app, scanning, or using a registered card.

- **Redemption:** Rewards start at 60 stars for items like modifications or lower-tier items, up to 200+ stars for standard drinks/food.

- **Birthday Reward:** A free item is provided, with redemption windows of 1 day (Green), 7 days (Gold), or 30 days (Reserve).

- **Bonus Stars:** Double stars are awarded on "Double Star Days" and when using a personal cup.

- **International:** US members can earn stars at participating Canada stores, with no currency exchange rate applied to star calculation. 

**Reimagined Program Launch Info:**  
Members are placed into tiers based on 2025 earnings, with status valid for 12 months. 


