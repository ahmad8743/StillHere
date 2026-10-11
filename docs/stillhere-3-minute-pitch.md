# StillHere: three-minute Hack Midwest pitch

## Recording approach

Keep the working app on screen throughout. Use a small camera overlay if you want judges to see you speaking, positioned away from the buttons and results. Follow one imagined parent from the question of where to sleep tonight into the next two weeks of expenses. This is a fictional demonstration, not a survivor testimonial.

The main script has 377 spoken words, before adding the pending sponsor lines below. Aim to finish around 2:55, including clicks and short pauses. The time marks are rehearsal targets.

## Script and screen actions

### 0:00 to 0:35: The problem and its scale

**On screen:** Start on Home with the fictional New Orleans hurricane notice visible. Look at the camera for the imagined child’s question, then leave a brief pause. Keep the app visible.

> Imagine your child asking, “Where are we sleeping tonight?”
>
> You’ve just left your home after a hurricane. You have three hundred dollars, your ID is gone, and you don’t know which help you can actually get.
>
> The National Oceanic and Atmospheric Administration recorded twenty-seven billion-dollar U.S. weather and climate disasters in 2024. We wanted to build something for the person trying to get through the days that follow.

### 0:35 to 0:45: The solution

**On screen:** Stay on Home. Point briefly to the recovery entry and Money and bills.

> StillHere helps someone work through what they need now, what’s stopping them from getting help, and how far their available money will go.

### 0:45 to 1:00: The proposed business model

**On screen:** Keep Home visible. Deliver this part plainly, without a long sales explanation.

> We propose keeping it free for survivors. Recovery nonprofits and local agencies would pay for an annual software license, starting with one partner pilot to validate the approach.

### 1:00 to 1:45: Recovery walkthrough

**On screen:** Click Yes, I’m affected → Yes, I’m safe for now. Select Somewhere safe to stay and Food and water → Continue. Select Getting there and Missing ID or Social Security documents → Continue. Pause on the next steps.

> Here’s how StillHere works. Let’s say I live in Louisiana, which recently endured a hurricane. The app sent me a notification as soon as the hurricane was detected and asked whether I needed help.
>
> We check immediate safety first.
>
> Then I can choose somewhere to stay and food together. I don’t have to decide which need to leave out.
>
> Next, I can say I’ve lost my ID and don’t have transportation. A suggestion only helps if I can actually use it.
>
> The app saves those answers and outlines the next steps. I’m also given resource suggestions and guidance on how to apply, taking my current limitations into account.

### 1:45 to 2:35: The financial demonstration

**On screen:** Click Home → Open budget. Show No new support. Scroll to Compare options → Coverage + aid on day 8 → Coverage + aid on day 12. Pause on each result. The exact figures below require the untouched $300 synthetic fixture.

> For Flex’s FinTech challenge, we built this budget to show how long my three hundred dollars will last.
>
> With these sample costs, I’m short on day five.
>
> Suppose food and lodging are covered for a week, and five hundred dollars from one of the suggested aid programs that StillHere helped me apply for arrives on day eight. The forecast shows those two weeks are covered.
>
> Move the same payment to day twelve, and I’m short on day eleven.
>
> For this parent, that could mean another night they can’t afford, even with help on the way. Seeing the gap early gives them a chance to plan for it.

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

The Flex mention is included in the financial walkthrough. The other lines below are drafts to finalize against Ahmad’s latest demo build. The local checkout still documents Strands/Bedrock and Akamai deployment as pending.

The requirements below come from [Hack Midwest’s published challenge descriptions](https://www.hackmidwest.com/), under Platform Challenges.

### AWS: Strands Agents SDK

The challenge requires actual SDK integration. Our documented design uses Strands to coordinate the agent and its allowed tools, with Amazon Bedrock supplying the model. Confirm which tools actually work in the demonstrated build before describing their behavior.

Possible narration, once confirmed: “Our agent uses the AWS Strands Agents SDK with Amazon Bedrock to call tools that read and update the recovery case.” Adjust the named tools to the demonstrated implementation.

### Akamai Cloud AI Challenge

The challenge requires an AI application using Akamai Cloud resources or inference. Our documented plan hosts the application and its data on Akamai Cloud; the current local checkout does not establish deployment.

Possible narration, once confirmed: “StillHere’s frontend and agent backend run on Akamai Cloud.” Include only the components actually deployed there.

Put the confirmed AWS and Akamai lines together just before the closing. Allow about 15 seconds and shorten the existing narration to make room within three minutes. If these integrations remain pending, use planned wording and do not describe them as completed challenge integrations.

### Flex: Best FinTech App

Flex sponsors the fintech category. Its published brief asks for creative use of fintech and does not list a required Flex API. Our working contribution is the 14-day forecast, comparison of aid timing, and reviewed money updates. Plaid Sandbox supplies the optional synthetic bank connection.

The main script names Flex while demonstrating the budget. If showing the connected test-bank section, an optional line is: “Plaid Sandbox lets us review synthetic bank balances before copying them into the budget.”

### USDA: Closure Call

The published USDA challenge concerns weather-driven federal facility closure recommendations and employee notifications. It calls for live National Weather Service data, a supplementary operational signal, a facility model, reasoned recommendations, and a reconstructable decision record.

The current survivor walkthrough does not demonstrate that workflow. A NOAA statistic or a weather notice alone does not establish this challenge’s requirements. Confirm whether Ahmad built a separate facility workflow before adding a USDA claim.

If that workflow exists, reserve a short demonstration of its actual closure recommendation and employee notification package. Write its narration from the working feature; do not describe household recovery guidance as facility closure decision support.

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

The business model is a proposal for discussion. There are no confirmed paying customers or partner pilots in this draft. The proposed first customer is a disaster recovery nonprofit or local agency; annual licensing and any future staff workflow would need validation.

This script reflects the current P2 prototype: guided selections, separate locally saved conversations, example next steps, and a working deterministic finance engine. The hurricane notice and budget are synthetic. Resource availability, eligibility, and aid payments are not verified or guaranteed.

The current checkout documents P1 agent integration and deployment as pending. Before filming a final integrated product, confirm the latest P1 status and replace the example-guidance sentence if the demonstrated capability has changed. Mention Strands, Bedrock, or Akamai only for integrations actually present in the build being shown.

Plaid Sandbox is an implemented optional connector with synthetic bank data. It is outside the main walkthrough to keep the recording within three minutes; leave bank login and the other secondary screens for follow-up questions.

## Sources for the statistic and optional supporting context

- **27 disasters:** NOAA NCEI, [Assessing the U.S. Climate in 2024](https://www.ncei.noaa.gov/news/national-climate-202413), published January 10, 2025. It reports 27 U.S. weather and climate disasters in 2024, each exceeding $1 billion in losses. This is a dated measure of disaster scale, not a market-size estimate.
- **Optional financial context, outside this script:** Federal Reserve, [Economic Well-Being of U.S. Households in 2025](https://www.federalreserve.gov/publications/files/2025-report-economic-well-being-us-households-202605.pdf), published May 2026, printed page 45 / PDF page 49. Twelve percent of all U.S. adults said they could not pay a hypothetical $400 emergency expense by any means. The figure concerns all adults, not specifically disaster survivors.
- **Pitch format:** [Hack Midwest official rules](https://www.hackmidwest.com/), under Rules, Pitching Your App (Sunday), and No Slide Decks. The pitch must show the prototype; slide decks are prohibited.

## Product references

The current implementation boundaries are documented in [README](../README.md) and [contracts and progress](contracts-and-progress.md). The starting ledger is in [fixtures](../frontend/fixtures.js); the four comparison scenarios are in [the finance engine](../frontend/finance-engine.js).

