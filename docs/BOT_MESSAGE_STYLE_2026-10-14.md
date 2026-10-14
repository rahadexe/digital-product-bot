# Clean bot structure and message recommendations

Scope: source review of the main menu, account, product, deposit and delivery messages, plus Telegram platform documentation and Nielsen Norman Group guidance. The Wallet and Account flows below are implemented; the remaining recommendations have not been validated in a live Telegram usability test.

Keep the four main destinations: Shop, Wallet, Support, Account. Use a stable reply keyboard for those destinations and contextual inline actions inside each screen. Do not force the keyboard to be reattached by sending an empty or emoji-only message after each transaction. Preserve receipts and delivery records independently from disposable browsing messages.

Telegram recommends editing existing inline keyboards/messages for navigation rather than repeatedly sending and deleting messages. Inline callback buttons do not insert the button text into the chat. Source: https://core.telegram.org/bots/features#inline-keyboards

Use progressive disclosure: keep frequently needed information visible; place referrals, API settings and long descriptions behind clearly named secondary actions. Source: https://www.nngroup.com/articles/progressive-disclosure/

## Writing review

| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| MEDIUM | app/bot/handlers/shop.py:282, app/bot/handlers/shop.py:517, app/bot/handlers/shop.py:1112 | Different product formats across entry paths; repeated balance, labels and instructions | One product template: title, duration, price, actual availability/delivery mode; details behind a button | Consistent vocabulary and presentation make buying predictable |
| MEDIUM | app/bot/handlers/shop.py:355, app/bot/handlers/shop.py:1328, app/services/delivery.py:63 | Purchase Successful / Order Placed / Order Successful with differing formatting | Order placed → Preparing delivery → Delivered; keep payment status separate | Consistent state vocabulary avoids confusing payment with delivery |
| LOW | app/bot/handlers/shop.py:289, app/bot/handlers/shop.py:1119 | Repeated instructions to tap visibly labelled buttons | Descriptive buttons such as Buy · ৳180 and Change quantity; instructions only for unfamiliar input | Remove redundant copy without hiding the next step |

## Proposed screen content

| Screen | Visible content | Secondary actions |
| --- | --- | --- |
| Home | Store name, one-line purpose, current balance | Stable four-button main menu |
| Shop | Search and categories; product names with prices | Pagination and back |
| Product | Name, duration, price, real delivery mode and availability | Details, quantity, buy with total price |
| Wallet | Balance and payment-method prompt | Inline payment methods, instant payment, History |
| Deposit instructions | Method, account type/number, minimum, essential instructions | I've Paid, Back; then collect amount and transaction ID |
| Account | Account ID, name, balance, order count, spent amount, Member/Reseller status, referral count/earnings and the referral link | Inline Orders, Referral, API and Language actions; Referral opens detailed referral history; Reseller opens the application for customers and the reseller hub for approved accounts |
| Language | English is available now | Bangla is marked Coming soon |
| Support | Choose order help or payment help | Contact support with the relevant order/deposit reference |

API access belongs to every customer; reseller benefits remain separate. Important warranty/restriction information that affects the decision must remain visible before purchase, even when other details are collapsed.

## Voice and layout rules

Wallet keeps the main reply keyboard unchanged. Payment methods and History are inline under the balance; selecting a manual method edits that message to show its instructions and the **I've Paid** / **Back** actions. Tapping **I've Paid** starts the amount and transaction-ID prompts. This avoids replacing the main keyboard with a second, wallet-specific reply keyboard.

Account also uses inline actions without replacing the main reply keyboard. Keep referral summary and link on the profile card; put detailed referral history behind **Referral**. The Language screen shows English as available and Bangla as **Coming soon** until localization is ready.

- Sentence case, plain English consistent with the current bot language policy.
- One short bold title; regular-weight supporting text; code formatting only for values users need to copy.
- Usually zero or one meaningful emoji in a heading. Avoid icons on every field, all-caps buttons, decorative separators and repeated celebration messages.
- Aim for roughly 3–6 lines in routine cards; this is a design target, not a Telegram limit. Payment instructions and credentials may legitimately be longer.
- One main action per state. Use Back for the previous screen, Home for the root and Cancel only when it cancels the current operation.
- Show one primary currency for routine browsing; expose conversion where it matters for payment or a customer's chosen preference.
- Errors say what happened and what to do. Financial errors must distinguish no debit, confirmed debit, and unknown outcome. Never suggest a blind retry when the result is unknown.
- Update browsing/progress cards in place. Keep final deposit receipts, order receipts and delivered credentials. Do not delete evidence merely to make the chat look empty.
- Avoid repeated notifications for unchanged pending states. Notify on meaningful changes and provide a status action.

## Example copy (illustrative amounts)

Product:

    YouTube Premium
    1 month · ৳180
    Delivery: Automatic

    [Details] [Quantity: 1]
    [Buy · ৳180]
    [Back]

Deposit awaiting review:

    Deposit under review
    ৳500 · bKash · #D1048
    Your balance will update after verification.

    [View deposit] [Get help]

Unknown purchase result:

    Checking your order
    We haven't confirmed the result yet.
    Please don't place the same order again.

    [View order] [Get help]

Final delivery:

    Delivered · #1048
    YouTube Premium · 1 month
    Paid: ৳180

    Email: …
    Password: …

    [Copy details] [Get help]

Only show a copy action if the content fits the platform's supported limit; longer content should remain available in a readable delivery message/file. Product delivery labels must reflect the actual fulfillment path.

## Implementation order

1. Unify product, pending and final receipt templates across entry paths.
2. Make main navigation stable and use inline controls for in-screen actions.
3. Keep Account brief, put referral details behind Referral, and label unsupported languages as Coming soon.
4. Test one purchase, insufficient balance, deposit review, uncertain supplier outcome and return navigation on real Android/iOS Telegram clients. Measure message count per task and whether the next action is clear; revise based on observed use.

Writing review disposition: Approve for the inspected scope, with the medium/low improvements above. This is not approval of uninspected flows or a claim that the proposed design has been user-tested.

## Implementation update

Implemented the approved clean-message direction in the Python bot:

| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| Medium | Shop entry | Message entry replaced the root keyboard with category buttons | Categories use inline buttons for both entry types | Keep main navigation stable |
| Medium | Product entry | Text selections had a separate verbose card and reply keyboard | Share the same product view and quantity controls | Keep stock, reseller pricing and navigation consistent |
| Low | Product and quantity | Repeated balance, category and long quantity instructions | Product details, price, warranty, shortfall when needed, concise quantity prompt | Reduce scrolling |
| Low | Account | Referral totals/link and lifetime-spend content on every visit | Three-line name/tier, balance and order summary; referral details remain in Referral | Reduce clutter and skip an unnecessary referral query and bot-username lookup |
| Low | Account actions | Language offered despite English-only policy | Language hidden from the active account inline menu | Avoid an unavailable choice; legacy language callbacks retained |
| Medium | Wallet | Methods immediately shown on root entry | Balance, Add funds and Deposit history; pending review hides Add funds | Separate summary from payment selection while keeping review visible |
| Low | Purchase and delivery | Celebratory and repeated success labels | Order placed, Preparing delivery, Delivered; retain reference, paid amount and escaped credentials | Distinguish payment from actual fulfillment |

Configured currency preference remains respected. Customer API eligibility and reseller discount authorization are unchanged. Payment verification, purchase accounting and the durable delivery queue remain in place. This update does not deploy or restart the live bot.

The legacy deposit Confirm callback now requires the confirmation state. An old button cannot resubmit a deposit or clear the context needed to correct a mistyped TrxID. Regression fixtures use the current direct-submission flow. Integration testing also exposed local-payment credit being divided by the display exchange rate despite a BDT ledger. Local deposits now credit the actual BDT payment with a ledger conversion rate of 1; the success balance is labelled BDT.

Android/iOS visual verification and live provider delivery remain unverified. The example Copy details/Get help layout above is a design target, not a claim that every receipt now has those exact buttons.
