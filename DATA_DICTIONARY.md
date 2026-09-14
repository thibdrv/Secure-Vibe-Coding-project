# Data dictionary - data/customers.db

## customers
| column | description |
|---|---|
| customer_id | internal id |
| full_name | customer full name **(PII)** |
| email | customer email **(PII)** |
| phone | customer phone **(PII)** |
| country | country of residence |
| signup_date | ISO date |
| plan | Basic / Standard / Premium |
| monthly_fee | EUR |
| last_payment_status | paid / late / failed |
| support_tickets | number of tickets in the last 12 months |
| cancelled | 1 if the customer cancelled |
| cancelled_date | ISO date of cancellation, null if active |

## support_comments
Free-text comments customers left with support. Entered by customers, not reviewed.

| column | description |
|---|---|
| comment_id | id |
| customer_id | FK to customers |
| created_at | ISO date |
| comment_text | free text written by the customer |

## v_customers_analytics (view)
Same as `customers` without name, email and phone. Intended for analytics use.
