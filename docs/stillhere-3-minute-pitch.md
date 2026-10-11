# StillHere: three-minute Hack Midwest pitch

## Recording approach

Keep the working app on screen throughout. Use a small camera overlay if you want judges to see you speaking, positioned away from the buttons and results. Follow one imagined parent from the question of where to sleep tonight into the next two weeks of expenses. This is a fictional demonstration, not a survivor testimonial.

This recording draft has 365 spoken words and includes AWS Strands, Akamai Cloud, and Flex. Ahmad is finishing the backend; confirm the model provider, deployed components, and demonstrated agent tools before using the completed-build narration below. Aim to finish around 2:55, including clicks and short pauses. The time marks are rehearsal targets.

## Script and screen actions

### 0:00 to 0:30: The problem and its scale

**On screen:** Start on Home with the fictional New Orleans hurricane notice visible. Look at the camera for the imagined child’s question, then leave a brief pause. Keep the app visible.

> Imagine your child asking, “Where are we sleeping tonight?”
>
> You’ve just left your home after a hurricane. You have three hundred dollars, your ID is gone, and you don’t know which help you can actually get.
>
> The National Oceanic and Atmospheric Administration recorded twenty-seven billion-dollar U.S. weather and climate disasters in 2024.

### 0:30 to 0:42: The solution

**On screen:** Stay on Home. Point briefly to the recovery entry and Money and bills.

> StillHere helps someone work through what they need now, what’s stopping them from getting help, and how far their available money will go.

### 0:42 to 0:52: The proposed business model

**On screen:** Keep Home visible. Deliver this part plainly, without a long sales explanation.

> We propose keeping it free for survivors. Governments and recovery foundations would pay for annual licenses, starting with one partner pilot.

### 0:52 to 1:35: Recovery walkthrough

**On screen:** Click Yes, I’m affected → Yes, I’m safe for now. Select Somewhere safe to stay and Food and water → Continue. Select Getting there and Missing ID or Social Security documents → Continue. Pause on the next steps.

> Here’s how StillHere works. I’m in Louisiana after a hurricane. When I open the app, a notice asks whether I need help.
>
> We check immediate safety first.
>
> Then I can choose somewhere to stay and food together. I don’t have to decide which need to leave out.
>
> Next, I can say I’ve lost my ID and don’t have transportation. A suggestion only helps if I can actually use it with the current obstacles I have.
>
> The app saves those answers and outlines the next steps. I’m also given resource suggestions and guidance on how to apply, taking my current limitations into account.

### 1:35 to 2:20: The financial demonstration

**On screen:** Click Home → Open budget. Show No new support. Scroll to Compare options → Coverage + aid on day 8 → Coverage + aid on day 12. Pause on each result. The exact figures below require the untouched $300 synthetic fixture.

> For Flex’s FinTech challenge, we built this budget to show how long my three hundred dollars will last.
>
> With these sample costs, I’m short on day five.
>
> Suppose food and lodging are covered for a week, and five hundred dollars of aid arrives on day eight. That covers the listed costs for two weeks.
>
> Move the same payment to day twelve, and I’m short on day eleven.
>
> For this parent, that could mean another night they can’t afford, even with help on the way. Seeing the gap early gives them a chance to plan for it.

### 2:20 to 2:35: AWS and Akamai

**On screen:** Keep the app visible. This narration is for the completed integration; confirm it with Ahmad before recording.

> We use the AWS Strands Agents SDK with Amazon Bedrock to coordinate the agent’s tool calls. Our frontend and backend run on Akamai Cloud, including the agent runtime.

### 2:35 to 2:55: Return and close

**On screen:** Click Home → Continue chat to show the recovery context is still there. Look at the camera for the closing thought, with the app and StillHere name still visible.

> Returning to the recovery chat, I can continue without explaining everything again.
>
> We want to help that parent answer their child with a plan for tonight and a clearer idea of what comes next.
>
> I’m Raneem.
>
> And I’m Ahmad.
>
> And this is StillHere.

## Sponsor challenges and narration

The main script now names all three selected challenges. Its AWS and Akamai narration is prepared for the completed backend and deployment. Ahmad is finishing the backend; the current local checkout does not establish that those integrations or deployment are complete.

The requirements below come from [Hack Midwest’s published challenge descriptions](https://www.hackmidwest.com/), under Platform Challenges.

### AWS: Strands Agents SDK

The challenge requires actual SDK integration. Our documented design uses Strands to coordinate the agent and its allowed tools, with Amazon Bedrock supplying the model. Confirm which tools actually work in the demonstrated build before describing their behavior.

Possible narration, once confirmed: “Our agent uses the AWS Strands Agents SDK with Amazon Bedrock to call tools that read and update the recovery case.” Adjust the named tools to the demonstrated implementation.

### Akamai Cloud AI Challenge

The challenge requires an AI application using Akamai Cloud resources or inference. Our documented plan hosts the application and its data on Akamai Cloud; the current local checkout does not establish deployment.

Possible narration, once confirmed: “StillHere’s frontend and agent backend run on Akamai Cloud.” Include only the components actually deployed there.

The main script reserves 15 seconds for AWS and Akamai just before the closing. If either integration remains pending, use planned wording for that part. Backend completion and cloud deployment need separate confirmation.

### Flex: Best FinTech App

Flex sponsors the fintech category. Its published brief asks for creative use of fintech and does not list a required Flex API. Our working contribution is the 14-day forecast, comparison of aid timing, and reviewed money updates. Plaid Sandbox supplies the optional synthetic bank connection.

The main script names Flex while demonstrating the budget. If showing the connected test-bank section, an optional line is: “Plaid Sandbox lets us review synthetic bank balances before copying them into the budget.”

## Before recording

- Use a separate private browser window with a fresh synthetic case. Your current saved case includes reviewed test-bank balances, so its forecast can differ from the $300 example in this script. Do not reset that saved case just to film.
- Choose to share the demo city, New Orleans, Louisiana, before the take so the hurricane notice is visible. The notice is a fictional scenario.
- Rehearse the recovery selections and the two aid scenarios. The untouched fixture gives a first gap on day 5 without new support, no gap with coverage plus aid on day 8, and a day 11 gap with the same aid on day 12.
- Collapse the optional bank connection section and money-entry details before the take. Keep the summary and Compare options easy to reach.
- Speak while clicking. Give the day 12 result a short pause so judges can see the gap.
- Let the opening question land before continuing. Use your usual speaking voice, then become more practical as you show the app helping this fictional parent work through their situation.
- If you run long, cut the NOAA sentence first. Keep the recovery selections and the aid-delay comparison.
- Record a timed practice take. End the final sentence by 2:55 to leave a small buffer.

## Claims and scope

The business model is a proposal for discussion. There are no confirmed paying customers or partner pilots in this draft. The proposed customers are governments and recovery foundations; annual licensing and any future staff workflow would need validation.

This script reflects the current P2 prototype: guided selections, separate locally saved conversations, example next steps, and a working deterministic finance engine. The hurricane notice and budget are synthetic. Resource availability, eligibility, and aid payments are not verified or guaranteed.

Ahmad is finishing the backend. The recording draft anticipates the documented Strands/Bedrock integration and Akamai deployment. Confirm which agent tools, resource suggestions, and application guidance actually work in the final demo, and match the narration to those features. Automatic disaster detection and push notifications are not assumed by this script.

Plaid Sandbox is an implemented optional connector with synthetic bank data. It is outside the main walkthrough to keep the recording within three minutes; leave bank login and the other secondary screens for follow-up questions.

## Sources for the statistic and optional supporting context

- **27 disasters:** NOAA NCEI, [Assessing the U.S. Climate in 2024](https://www.ncei.noaa.gov/news/national-climate-202413), published January 10, 2025. It reports 27 U.S. weather and climate disasters in 2024, each exceeding $1 billion in losses. This is a dated measure of disaster scale, not a market-size estimate.
- **Optional financial context, outside this script:** Federal Reserve, [Economic Well-Being of U.S. Households in 2025](https://www.federalreserve.gov/publications/files/2025-report-economic-well-being-us-households-202605.pdf), published May 2026, printed page 45 / PDF page 49. Twelve percent of all U.S. adults said they could not pay a hypothetical $400 emergency expense by any means. The figure concerns all adults, not specifically disaster survivors.
- **Pitch format:** [Hack Midwest official rules](https://www.hackmidwest.com/), under Rules, Pitching Your App (Sunday), and No Slide Decks. The pitch must show the prototype; slide decks are prohibited.

## Product references

The current implementation boundaries are documented in [README](../README.md) and [contracts and progress](contracts-and-progress.md). The starting ledger is in [fixtures](../frontend/fixtures.js); the four comparison scenarios are in [the finance engine](../frontend/finance-engine.js).

