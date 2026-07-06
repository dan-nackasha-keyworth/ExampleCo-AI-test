# AI Build - Code Appendix

This appendix contains the full, real source code for the working AI
build - not simulated, not pseudocode. Every file below is copied
directly from the project repository at generation time. Company
configuration in this public version is the fictional "Example Co."
(see `config.py`); the real, company-named submission materials this
build was originally created for are delivered privately and are not
in this repo.

**Repo link:** https://github.com/dan-nackasha-keyworth/ExampleCo-AI-test

**Companion document:** `HOW_THE_AI_WORKS.md` (in the same repository)
gives a plain-English glossary of every pipeline stage and the literal
text of all three prompts, if reading prose first is more useful than
reading code first.

## How to run this

1. Install dependencies: `pip install anthropic python-dotenv`
2. Create a `.env` file in the project root containing
   `ANTHROPIC_API_KEY=sk-ant-...` (never committed - `.gitignore`
   excludes it)
3. Run the full dev-set batch: `python batch_runner.py --split dev`
4. Build the results dashboard from the output it just wrote:
   `python dashboard.py`
5. Open the generated `outputs/run_*.html` file in a browser

Every run is read-only against the sample data and writes to a new,
timestamped output file - nothing is ever mutated in place, so the
batch can be re-run as many times as needed without losing a prior
result.

## Files in this appendix

- `config.py`
- `pipeline.py`
- `batch_runner.py`
- `dashboard.py`
- `opus_comparison.py`
- `preview_server.py`
- `data/brand_guidelines.json`
- `data/mock_backend.json`
- `data/sample_messages.json` (excerpt - full file in repo)

## `config.py`

```python
"""
Demo-company-specific configuration for the message-routing pipeline.

Everything generic (the classify/extract/confidence/draft/guardrail
pipeline itself) lives in pipeline.py and reads from this object rather
than hardcoding company specifics. Swapping this file for a different
company's config should let the same pipeline code run unmodified -
this is a genuinely reusable demo, not one-off code, and the values
below describe "Example Co.", a fictional shipping/logistics company
standing in for the real prospective employer this was built for. It
is intentionally company-agnostic for anything public-facing; the real
company-specific submission is delivered separately and privately.
"""

CONFIG = {
    "company_name": "Example Co.",

    "categories": ["Service", "Success", "Sales"],

    # A representative set of Support categories, shaped by how real-world
    # shipping/logistics support intake forms are typically structured.
    # None of these correspond to Sales or Success - confirms that channel of
    # entry is Service/Support-shaped only; Success/Sales must be detected
    # from message content, not assumed from channel.
    "help_centre_categories": [
        "Labels",
        "Pickups",
        "Tracking & Delivery",
        "Claims",
        "Billing",
        "Cancel a Shipment",
        "Close Account",
        "All Other Queries",
    ],

    # Need-based signals that override channel-of-entry: these always
    # indicate retention risk and route to Success even if raised via
    # the Support channel.
    "retention_risk_signals": [
        "close account",
        "cancel account",
        "cancel my account",
        "cancel a shipment",
        "cancel shipment",
        "downgrade",
        "switching to a competitor",
        "leaving example co",
    ],

    # Sensitive topics: always route to Service, never auto-resolved,
    # regardless of confidence score.
    "sensitive_topics": [
        "refund",
        "chargeback",
        "compliance",
        "customs seizure",
        "rate dispute",
        "overcharge",
        "billing dispute",
        "gdpr",
        "data request",
        "legal",
        "data breach",
        "account breach",
        "cyberattack",
        "hacked",
        "unauthorized access",
    ],

    # $5K ARR threshold: total account revenue (subscription + shipping
    # margin), not subscription fees alone. On a subscription-only basis
    # nearly every self-serve account falls under $5K given typical
    # self-serve shipping-software tiers, which would break the threshold's
    # purpose - so this must be applied against total account revenue when
    # available.
    "arr_threshold_sales_ae": 5000,

    # Representative self-serve monthly tiers (GBP) for a shipping-software
    # company, used only to illustrate why subscription-only revenue can't
    # drive the ARR threshold.
    "self_serve_tiers_gbp_per_month": {"min": 29, "max": 199},

    # Confidence scoring bands (0-100 scale, see pipeline.py for the
    # additive rubric that produces the raw score).
    "confidence_bands": {"high": 80, "medium": 50},

    # Categories where a missing account/order reference is itself a
    # negative confidence signal (Service messages are almost always
    # about a specific shipment/order).
    "categories_expecting_reference": ["Service"],

    # Reference terminology per category, used only as a signal for the
    # confidence score (does the message actually use category-specific
    # language, or is it generic). Not an exhaustive taxonomy.
    "category_keywords": {
        "Service": [
            "hs code", "customs", "tracking", "label", "shipment", "order",
            "delivery", "duty", "tax", "courier", "package", "parcel",
            "refund", "chargeback", "compliance", "gdpr",
        ],
        "Success": [
            "qbr", "ebr", "renewal", "expand", "expansion", "scale",
            "scaling", "grow", "growth", "upgrade", "review", "account health",
            "onboarding", "enterprise", "new warehouse", "new brand",
        ],
        "Sales": [
            "pricing", "price", "plan", "demo", "trial", "quote", "discount",
            "compare", "comparison", "sign up", "signing up", "new customer",
            "setup fee", "contract terms",
        ],
    },

    # Budget reality check inputs (from the task brief), used by the
    # commercial cost model reporting, not by the pipeline itself.
    "budget": {
        "total_annual_budget": 600_000,
        "fte_costs": {
            "service": {"count": 30, "annual_cost": 15_000},
            "sales": {"count": 3, "annual_cost": 15_000},
            "cs": {"count": 5, "annual_cost": 18_000},
        },
        "monthly_volume_proxy": 6_000,
    },

    "models": {
        # Cheaper/faster model for classification + structured extraction.
        "classify_extract": "claude-haiku-4-5",
        # Stronger model reserved only for response drafting.
        "draft": "claude-sonnet-5",
        # Used for the agentic investigation step (tool-selection judgement
        # matters more here than in routine extraction, so it gets the
        # stronger model too - only triggered for low-confidence messages).
        "investigate": "claude-sonnet-5",
    },

    # Confidence bands at or below which the investigation agent triggers.
    "investigation_trigger_bands": ["low"],

    # Real-world entry channels: a typical shipping-software company's
    # website exposes a Support ("Help") inbound form and a separate Sales
    # ("Sales request") inbound form, both with real structure. "Success" is
    # a third, fictional/assumed channel modeling a plain inbox with no form
    # structure at all (e.g. a shared "success@" address given out ad hoc by
    # CSMs) - since there's no dedicated Success intake form in reality, this
    # models what actually happens instead: whatever loosely Success-shaped
    # traffic exists lands in an unstructured mailbox that in practice fills
    # up with a genuine mix of Service, Success, and Sales content, because
    # nothing about the channel itself signals which one a message is. Entry
    # channel is fed to classify_and_extract as a prior, not a determining
    # factor: Support-channel and Sales-channel messages lean strongly
    # toward their matching category, but Success-channel messages should
    # NOT be assumed Success just because of where they arrived - that
    # channel is deliberately modeled as the messiest and least predictive
    # of the three, so message content must do essentially all of the work
    # there. Existing customers also routinely use whichever form is in
    # front of them regardless of channel (e.g. an existing account asking
    # about upgrading often goes through the Sales form even though the real
    # need is a Success conversation) - so content must always be able to
    # override the channel prior, not just for Success.
    "entry_channels": ["Support", "Sales", "Success"],

    # Below this rule-based confidence score (see score_confidence), route
    # to a 4th "Team Lead Triage" queue for manual assignment rather than
    # guessing a category queue. Routed to an existing team lead/principal
    # role, not a new hire - this is a volume-reduction lever, not a
    # headcount ask. Chosen from the observed score distribution on the
    # validated dev run: scores of 0/15/20 (13/80 messages) reflect
    # essentially no positive confidence signal firing at all, vs. 35+
    # where at least one strong signal (e.g. a single confident category
    # read) is present - the largest natural gap in the distribution sits
    # between 20 and 35. Sensitive-topic and retention-risk overrides
    # still take unconditional precedence over this - see determine_queue.
    # Expected direction of travel: as classification accuracy improves
    # (more real data, better-tuned prompts), the share of messages
    # landing below this floor should fall - this queue's volume is a
    # maturity signal to track over time, not a fixed cost.
    "team_lead_triage_confidence_floor": 20,
}

```

## `pipeline.py`

```python
"""
Generic classify -> extract -> confidence -> draft -> guardrail pipeline.

Nothing in this file is company-specific - all company detail is read
from the config object passed in, so the same code should run for a
different company by swapping the config. See config.py for the
values used at demo time.
"""

import json
from pathlib import Path

import anthropic

BRAND_GUIDELINES_PATH = Path(__file__).parent / "data" / "brand_guidelines.json"
MOCK_BACKEND_PATH = Path(__file__).parent / "data" / "mock_backend.json"


def load_brand_guidelines():
    """Read fresh on every call (not cached at import time) so that
    updating the guidelines file changes the next draft immediately -
    an informal stand-in for a live brand-platform query (e.g. Frontify),
    without needing a real MCP connection for this demo."""
    try:
        with open(BRAND_GUIDELINES_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_mock_backend():
    """SYNTHETIC TEST DATA - stands in for live calls to the real company's
    own MCP server (tracking/rates/duty/label - already shipped) plus their
    CRM/billing system for account context. See the build plan's
    'test system vs. real system' table for the full mapping."""
    try:
        with open(MOCK_BACKEND_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"orders": {}, "accounts": {}}


INVESTIGATION_TOOLS = [
    {
        "name": "lookup_order_status",
        "description": (
            "Look up live shipment/tracking status for an order reference "
            "(carrier, last scan, destination). Returns not_found if the "
            "reference does not exist in the system - only call this with "
            "a reference that actually appears in the message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_reference": {"type": "string", "description": "The order/shipment reference, e.g. ORD-12345"},
            },
            "required": ["order_reference"],
            "additionalProperties": False,
        },
    },
    {
        "name": "lookup_account_context",
        "description": (
            "Look up account-level context (plan tier, account age, recent "
            "ticket volume, ARR band) associated with an order reference. "
            "Returns not_found if there is no account on file for that "
            "reference - only call this with a reference that actually "
            "appears in the message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_reference": {"type": "string", "description": "The order/shipment reference to look up the associated account for"},
            },
            "required": ["order_reference"],
            "additionalProperties": False,
        },
    },
]


def _execute_investigation_tool(tool_name, tool_input, backend):
    ref = tool_input.get("order_reference", "")
    if tool_name == "lookup_order_status":
        record = backend.get("orders", {}).get(ref)
    elif tool_name == "lookup_account_context":
        record = backend.get("accounts", {}).get(ref)
    else:
        return json.dumps({"error": f"unknown tool {tool_name}"})
    return json.dumps(record) if record else json.dumps({"status": "not_found"})


def investigate_uncertain_message(client, message_text, extraction, config, max_iterations=4):
    """The one agentic component in this build - everything
    else is a deterministic workflow (see Architecture). For messages
    the base pipeline is uncertain about, the model decides for itself
    which read-only lookups (if any) are worth making before a human
    reviews the message, rather than a fixed, prescribed sequence.

    Prudent by construction: read-only tools only (no ability to send,
    modify, or action anything), a bounded iteration cap, triggered only
    on a narrow subset of messages (not the full batch), and the output
    is advisory text fed into the same human-review step that already
    exists - it never bypasses "nothing auto-sent without review"."""
    backend = load_mock_backend()
    system_prompt = (
        "You are helping a human support reviewer triage an uncertain "
        "customer message. You have two read-only lookup tools available. "
        "Decide for yourself whether either is worth calling, based on "
        "what the message actually contains - do not call a tool with a "
        "reference you are guessing at or inventing. If the message has "
        "no usable reference, say so plainly rather than calling a tool "
        "anyway. When you are done, write a short (2-3 sentence) note for "
        "the human reviewer summarising what you found and what it means "
        "for handling this message."
    )
    messages = [{
        "role": "user",
        "content": (
            f"Message: {message_text}\n\n"
            f"Extracted account/order reference (if any): "
            f"{extraction['account_or_order_reference'] or 'none found'}"
        ),
    }]

    usage = []
    for _ in range(max_iterations):
        response = client.messages.create(
            model=config["models"]["investigate"],
            max_tokens=500,
            thinking={"type": "disabled"},
            system=system_prompt,
            tools=INVESTIGATION_TOOLS,
            messages=messages,
        )
        usage.append({
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "model": config["models"]["investigate"],
        })
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_text = next((b.text for b in response.content if b.type == "text"), "")
            return final_text, usage

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = _execute_investigation_tool(block.name, block.input, backend)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        messages.append({"role": "user", "content": tool_results})

    return "Investigation did not conclude within the iteration limit.", usage


EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": ["Service", "Success", "Sales"],
            "description": "The single best-fitting category for this message.",
        },
        "category_alternatives": {
            "type": "array",
            "items": {"type": "string", "enum": ["Service", "Success", "Sales"]},
            "description": "Any other categories that are also plausible. Empty if the message clearly fits only one category.",
        },
        "contradictory_signals": {
            "type": "boolean",
            "description": "True only if the message contains language pulling toward two categories at once (not just an aside), not merely because it mentions more than one topic.",
        },
        "account_or_order_reference": {
            "type": "string",
            "description": "The order or account reference mentioned in the message (e.g. an order number), or an empty string if none is present.",
        },
        "issue_type": {
            "type": "string",
            "description": "A short (2-6 word) label for what the message is actually about, e.g. 'customs delay' or 'renewal discussion'.",
        },
        "sentiment": {
            "type": "string",
            "enum": ["positive", "neutral", "negative", "mixed"],
        },
        "urgency": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
        "expansion_intent_language": {
            "type": "boolean",
            "description": "True if the message contains language suggesting the customer wants to grow, scale, or expand their use of the platform.",
        },
        "retention_risk_language": {
            "type": "boolean",
            "description": "True if the message explicitly asks to close or cancel the account, cancel a shipment, or contains language threatening or seriously considering leaving/switching away from the company - even if phrased as frustration rather than a formal request.",
        },
        "sensitive_topic_flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Only topics from the provided sensitive-topics reference list that are clearly present. Ordinary shipping, tracking, or service issues are NOT sensitive topics on their own, even if urgent or the customer is upset. Empty if none of the listed topics apply.",
        },
        "matched_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Category-specific reference terms from the provided keyword list that clearly appear in or are closely paraphrased by the message.",
        },
        "message_length_words": {
            "type": "integer",
            "description": "Approximate word count of the original message.",
        },
        "reasoning": {
            "type": "string",
            "description": "One or two sentences on why this category and these signals were chosen.",
        },
    },
    "required": [
        "category", "category_alternatives", "contradictory_signals",
        "account_or_order_reference", "issue_type", "sentiment", "urgency",
        "expansion_intent_language", "retention_risk_language",
        "sensitive_topic_flags", "matched_keywords", "message_length_words", "reasoning",
    ],
    "additionalProperties": False,
}


def classify_and_extract(client, message_text, config, entry_channel=None):
    """Single Haiku call: classify + extract structured fields.

    Ground truth is never included in this prompt - only the message
    text and generic config-driven instructions, per the re-run safety
    design (no train/test contamination).
    """
    keyword_lines = "\n".join(
        f"- {cat}: {', '.join(terms)}"
        for cat, terms in config["category_keywords"].items()
    )
    sensitive_topics_line = ", ".join(config["sensitive_topics"])
    channel_block = ""
    if entry_channel == "Success":
        channel_block = (
            f"\nEntry channel prior: this message was submitted via "
            f"{config['company_name']}'s Success mailbox. Unlike the Support "
            f"and Sales forms, this is a plain, unstructured inbox with no "
            f"form fields guiding what gets sent there - in practice it "
            f"fills up with a genuine mix of Service, Success, and Sales "
            f"content, because nothing about the channel itself signals "
            f"which one a message is. Treat this channel as carrying "
            f"essentially no predictive value for category - do not lean on "
            f"it at all, and classify based on message content alone as you "
            f"would with no entry channel provided.\n"
        )
    elif entry_channel:
        channel_block = (
            f"\nEntry channel prior: this message was submitted via "
            f"{config['company_name']}'s {entry_channel} inbound form. "
            f"There is no dedicated Success form - Support-channel messages "
            f"are usually Service issues, Sales-channel messages are usually "
            f"Sales, but existing customers often use whichever form is in "
            f"front of them (e.g. an existing account asking about "
            f"upgrading frequently goes through the Sales form even though "
            f"the real need is a Success conversation). Treat entry channel "
            f"as a helpful prior, never as a determining factor - if the "
            f"message content clearly points to a different category, "
            f"trust the content over the channel.\n"
        )
    system_prompt = (
        f"You classify inbound customer messages for {config['company_name']}, "
        f"a shipping software company, into exactly one of: "
        f"{', '.join(config['categories'])}.\n\n"
        f"Service = support/logistics issues (shipping, tracking, labels, "
        f"customs, billing problems, refunds, compliance).\n"
        f"Success = existing customer wanting a business review, renewal "
        f"discussion, or to grow/expand their usage.\n"
        f"Sales = a prospect or existing customer asking about pricing, "
        f"plans, or signing up for something new.\n"
        f"{channel_block}\n"
        f"Reference terminology per category (a hint, not an exhaustive "
        f"list):\n{keyword_lines}\n\n"
        f"retention_risk_language: set this true for explicit close/cancel "
        f"account or shipment requests, phrases like: "
        f"{', '.join(config['retention_risk_signals'])}, and also for "
        f"softer but real language about leaving or switching providers "
        f"even without a formal cancellation request. This exists so "
        f"retention risk routes correctly regardless of how it's phrased. "
        f"It requires the message to actually contain leaving/switching/"
        f"cancelling/downgrading language, however soft - anger, frustration, "
        f"or a customer describing themselves as a 'paying customer' who "
        f"deserves better is NOT by itself retention risk, even if strongly "
        f"worded, unless the message also expresses an intent to leave or "
        f"reconsider the relationship. Example that should NOT be flagged: "
        f"'this is ridiculous for a paying customer, please fix it' (angry, "
        f"but no leaving/switching language). Example that SHOULD be "
        f"flagged: 'if this keeps happening we'll have to look at other "
        f"providers' (soft but real switching language).\n\n"
        f"sensitive_topic_flags is a NARROW field. Only use terms from this "
        f"exact list, and only when clearly present: {sensitive_topics_line}. "
        f"Match the FULL concept, not a substring - the word 'customs' "
        f"appearing anywhere does NOT mean 'customs seizure' applies; that "
        f"term means customs authorities are actively holding, confiscating, "
        f"or refusing to release the goods right now - not a routine customs "
        f"question, a delay, a documentation request, or a shipment that has "
        f"already been returned to sender. A return-to-sender caused by a "
        f"paperwork or documentation mismatch is a completed logistics "
        f"outcome to troubleshoot, not an active seizure or compliance hold - "
        f"do not flag it even though customs was involved in causing it. "
        f"Likewise 'overcharge'/'rate dispute' require the customer actually "
        f"disputing a charge as wrong or unacceptable, not just asking about "
        f"or being surprised by a duty/rate amount, and not a neutral, "
        f"matter-of-fact report of a duplicate charge or data-entry mistake "
        f"with no disputing language - but DO flag it if the customer frames "
        f"the charge as wrong, unacceptable, ridiculous, or otherwise objects "
        f"to it, even without a formal dispute process invoked. 'Compliance' "
        f"requires the customer themselves to raise an actual regulatory, "
        f"legal, or compliance concern (using language like 'compliance', "
        f"'breaching', 'regulation', 'legal requirement', or asking what's "
        f"required to stay compliant for a controlled/restricted product) - "
        f"not a routine logistics complaint about a restricted item's "
        f"shipping status being confusing, inconsistent, or blocked without "
        f"explanation, where the customer is not themselves invoking "
        f"compliance/regulatory language. A message being urgent, negative, "
        f"or about a real logistics problem (a late shipment, a tracking "
        f"issue, a stuck customs clearance, a shipment returned to sender, an "
        f"HS code question, a rate discrepancy to be looked into, a "
        f"restricted-item shipment blocked or flagged inconsistently with no "
        f"compliance/regulatory language from the customer) is NOT by itself "
        f"a sensitive topic - leave this field empty unless one of the "
        f"listed topics specifically and fully applies. Examples that "
        f"should NOT be flagged: 'my package is stuck in customs, what "
        f"documents do I need' (routine hold, still in progress, no "
        f"confiscation), 'the rate charged doesn't match the quote, please "
        f"check' (routine discrepancy, not a dispute), 'my order was "
        f"returned to sender because the customs paperwork didn't match the "
        f"contents, what went wrong' (routine documentation mismatch - the "
        f"goods were sent back, not confiscated or held), 'we got charged "
        f"twice for the same label by mistake' (a billing error to correct, "
        f"not a disputed overcharge), 'a restricted item got flagged then "
        f"unflagged then flagged again, which is it' (a confusing status to "
        f"clarify, not a compliance dispute). Examples that SHOULD be "
        f"flagged: 'I want a refund', 'I'm disputing this charge as wrong "
        f"and want it reversed', 'this is a GDPR data request', 'we were "
        f"charged twice and this is ridiculous for a paying customer' (the "
        f"customer is objecting to the charge, not neutrally reporting it), "
        f"'what compliance documentation do we need, we want to make sure "
        f"we're not breaching anything' (the customer is themselves raising "
        f"a compliance/regulatory concern, not just asking why a shipment is "
        f"blocked). Note the two 'charged twice' examples above differ only "
        f"in tone, not facts - both describe the same kind of duplicate "
        f"charge, but one reports it neutrally ('by mistake', no objection) "
        f"and the other objects to it ('ridiculous', a paying customer being "
        f"treated unfairly). Any negative, objecting adjective attached to "
        f"the charge itself - ridiculous, unacceptable, wrong, unfair, a "
        f"joke, outrageous - is disputing language on its own, even paired "
        f"with an unrelated complaint like a slow response, and is enough "
        f"to flag it; don't let a plausible neutral reading of a similar-"
        f"sounding example override actual objecting words in this "
        f"message.\n\n"
        f"Be honest about ambiguity: if a message clearly fits more than "
        f"one category, say so via category_alternatives and "
        f"contradictory_signals rather than forcing false confidence."
    )

    response = client.messages.create(
        model=config["models"]["classify_extract"],
        max_tokens=1024,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": message_text}],
        output_config={"format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
    )

    text = next(b.text for b in response.content if b.type == "text")
    extraction = json.loads(text)
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "model": config["models"]["classify_extract"],
    }
    return extraction, usage


def score_confidence(extraction, config):
    """Rule-based 0-100 confidence score from defined signals.

    Deliberately not asked of the model as a percentage - every
    contributing signal here is visible and independently checkable.
    """
    score = 0
    reasons = []

    if extraction["account_or_order_reference"]:
        score += 35
        reasons.append("+35 account/order reference present")

    single_category = (
        not extraction["contradictory_signals"]
        and len(extraction["category_alternatives"]) == 0
    )
    if single_category:
        score += 35
        reasons.append("+35 single fitting category, no hedging")

    if extraction["matched_keywords"]:
        score += 15
        reasons.append("+15 category-specific terminology matched")

    if extraction["sentiment"] != "mixed":
        score += 15
        reasons.append("+15 sentiment/urgency stated unambiguously")

    if extraction["contradictory_signals"]:
        score -= 40
        reasons.append("-40 contradictory category signals")

    expects_reference = extraction["category"] in config["categories_expecting_reference"]
    if expects_reference and not extraction["account_or_order_reference"]:
        score -= 30
        reasons.append("-30 no reference where category normally expects one")

    if extraction["message_length_words"] < 8:
        score -= 20
        reasons.append("-20 message very short/generic")

    if len(extraction["category_alternatives"]) > 0 and not extraction["contradictory_signals"]:
        score -= 15
        reasons.append("-15 multiple categories plausible")

    score = max(0, min(100, score))

    bands = config["confidence_bands"]
    if score >= bands["high"]:
        band = "high"
    elif score >= bands["medium"]:
        band = "medium"
    else:
        band = "low"

    return {"score": score, "band": band, "reasons": reasons}


def determine_queue(extraction, confidence, config=None):
    """Guardrail routing: sensitive topics and retention risk override
    the raw category; contradictory signals escalate to Success; very
    low confidence routes to a 4th Team Lead Triage queue for manual
    assignment rather than guessing a category queue; low confidence
    (more broadly) routes to human review regardless of category.

    Sensitive-topic and retention-risk overrides are unconditional -
    they win even when confidence is at the Team Lead Triage floor, since
    those are safety/retention wins that must never be downgraded to
    "unassigned". Team Lead Triage only applies to the residual case: no
    guardrail fired, but the raw category guess itself is too weak to
    trust (see config's team_lead_triage_confidence_floor for how the
    threshold was chosen).

    Multi-team loop-in: some messages need more than one
    team's awareness at once (a real support issue, a retention risk,
    an expansion mention, all in one message). Rather than splitting
    ownership - the classic "everyone owns it, no one owns it" failure -
    a single primary queue is always kept, and any other team with a
    independently detected signal is added to a loop_in list
    instead of taking ownership. This is a distinct mechanism from
    category_alternatives/contradictory_signals, which represent
    uncertainty about which single category applies, not confirmed
    multiple simultaneous needs."""
    guardrail_flags = []
    config = config or {}

    is_sensitive = bool(extraction["sensitive_topic_flags"])
    is_retention_risk = extraction["retention_risk_language"]
    triage_floor = config.get("team_lead_triage_confidence_floor", -1)

    if is_sensitive:
        queue = "Service"
        guardrail_flags.append("sensitive_topic_always_service")
    elif is_retention_risk:
        queue = "Success"
        guardrail_flags.append("retention_risk_override_to_success")
    elif extraction["contradictory_signals"]:
        queue = "Success"
        guardrail_flags.append("contradictory_signals_escalated_to_success")
    elif confidence["score"] <= triage_floor:
        queue = "Team Lead Triage"
        guardrail_flags.append("team_lead_triage_low_confidence_floor")
    else:
        queue = extraction["category"]

    loop_in = []
    underlying_category = extraction["category"]
    if queue != underlying_category:
        # Ownership moved away from the raw category via a guardrail
        # override (retention risk, contradiction) - the underlying need
        # (e.g. a real shipment problem) is still real and must not be
        # lost just because Success now owns the conversation.
        loop_in.append(underlying_category)
    if is_retention_risk and queue != "Success":
        # Sensitive topic took precedence for ownership, but Success
        # still needs visibility into the retention risk.
        loop_in.append("Success")
    if extraction["expansion_intent_language"] and queue != "Success":
        loop_in.append("Success")
    for alt in extraction["category_alternatives"]:
        if alt != queue:
            loop_in.append(alt)
    loop_in = sorted(set(loop_in) - {queue})

    if loop_in:
        guardrail_flags.append(f"looped_in:{','.join(loop_in)}")

    if confidence["band"] == "low":
        guardrail_flags.append("low_confidence_human_review")

    # Phase-1 scope: every first message in a thread is human-approved
    # before anything is sent, regardless of confidence band. The bands
    # only affect review priority/flagging shown in the dashboard.
    review_priority = "urgent" if (is_sensitive or confidence["band"] == "low") else "standard"

    return {
        "queue": queue,
        "loop_in": loop_in,
        "guardrail_flags": guardrail_flags,
        "review_priority": review_priority,
        "requires_human_review": True,
    }


def health_expansion_flag(extraction, routing):
    """Lightweight, rule-based (no extra API call) health/expansion
    signal on the Success branch only. Explicitly text-only - not a
    verified account health score. "Success branch" now means Success
    has visibility at all, whether as primary owner or looped in on a
    message another team owns - the expansion signal is just as real
    either way."""
    success_involved = routing["queue"] == "Success" or "Success" in routing.get("loop_in", [])
    if not success_involved or not extraction["expansion_intent_language"]:
        return None
    return {
        "flag": "possible_expansion_signal",
        "note": (
            "Message contains expansion-intent language. This is a "
            "text-only signal derived from this single message, not a "
            "verified account health score - treat as a prompt to look "
            "closer, not a conclusion."
        ),
    }


def draft_response(client, message_text, extraction, confidence, routing, config):
    """Sonnet call: a conditional draft. If key info is missing, the
    draft is a clarification request, not a forced resolution. Thinking
    is disabled - this is a short drafting task, not one that benefits
    from extended reasoning, and leaving it on would inflate cost."""
    needs_clarification = (
        routing["queue"] == extraction["category"] == "Service"
        and extraction["category"] in config["categories_expecting_reference"]
        and not extraction["account_or_order_reference"]
    )

    if needs_clarification:
        instruction = (
            "Key information is missing (no order/account reference). "
            "Draft a brief, polite reply asking the customer for that "
            "specific missing detail. Do not attempt to resolve the issue."
        )
    elif routing["queue"] == "Team Lead Triage":
        # Confidence was too low to trust an auto-routed queue, so this
        # draft uses the model's best-guess category only as a starting
        # point for whichever team the team lead assigns it to manually -
        # it is not itself a routing decision.
        instruction = (
            f"Draft a brief, helpful reply addressing: {extraction['issue_type']}. "
            f"This message's queue assignment is uncertain and pending manual "
            f"review by a team lead, so treat {extraction['category']} as a "
            f"best guess only, not a confirmed team. This is a draft for "
            f"human review before sending, not a final answer."
        )
    else:
        instruction = (
            f"Draft a brief, helpful reply for the {routing['queue']} team "
            f"to send this customer, addressing: {extraction['issue_type']}. "
            f"This is a draft for human review before sending, not a final answer."
        )

    brand = load_brand_guidelines()
    if brand:
        banned = ", ".join(brand.get("banned_words_or_phrases", []))
        voice_lines = "\n".join(f"- {v}" for v in brand.get("voice_principles", []))
        ai_isms = brand.get("avoid_ai_isms", {})
        ai_ism_words = ", ".join(ai_isms.get("banned_words", []))
        ai_ism_phrases = ", ".join(ai_isms.get("banned_phrases", []))
        ai_ism_style = "\n".join(f"- {s}" for s in ai_isms.get("style_rules", []))
        brand_block = (
            f"\n\nBrand guidelines for {config['company_name']} (follow these exactly):\n"
            f"Tone: {brand.get('tone', '')}\n"
            f"Voice principles:\n{voice_lines}\n"
            f"Never use these words/phrases: {banned}\n"
            f"Formatting: {brand.get('formatting', '')}\n"
            f"Sign off with: {brand.get('preferred_phrases', {}).get('sign_off', '')}\n\n"
            f"Separately, avoid AI-isms - words and patterns that read as AI-generated "
            f"rather than human-written:\n"
            f"Never use these words: {ai_ism_words}\n"
            f"Never use these phrases: {ai_ism_phrases}\n"
            f"Style rules:\n{ai_ism_style}"
        )
    else:
        brand_block = ""

    system_prompt = (
        f"You draft short customer-support replies for {config['company_name']}. "
        f"Keep it to 2-4 sentences unless technical detail requires more, no filler."
        f"{brand_block}"
    )

    response = client.messages.create(
        model=config["models"]["draft"],
        max_tokens=400,
        thinking={"type": "disabled"},
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": f"Original message: {message_text}\n\nInstruction: {instruction}",
        }],
    )

    draft_text = next(b.text for b in response.content if b.type == "text")
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "model": config["models"]["draft"],
    }
    return draft_text, usage, needs_clarification


def process_message(client, message, config):
    """Run one message through the full pipeline. Returns a structured
    result dict; never raises on model/parse errors - falls back to
    human review so the batch always completes (safe degradation)."""
    try:
        extraction, extract_usage = classify_and_extract(
            client, message["text"], config, entry_channel=message.get("entry_channel"),
        )
    except (anthropic.APIError, json.JSONDecodeError, StopIteration) as e:
        return {
            "id": message["id"],
            "text": message["text"],
            "error": f"{type(e).__name__}: {e}",
            "queue": "Service",
            "guardrail_flags": ["extraction_failed_defaulted_to_human_review"],
            "requires_human_review": True,
            "usage": [],
        }

    confidence = score_confidence(extraction, config)
    routing = determine_queue(extraction, confidence, config)
    health_flag = health_expansion_flag(extraction, routing)

    try:
        draft_text, draft_usage, is_clarification = draft_response(
            client, message["text"], extraction, confidence, routing, config,
        )
        usage = [extract_usage, draft_usage]
    except (anthropic.APIError, StopIteration) as e:
        draft_text = None
        is_clarification = None
        usage = [extract_usage]
        routing["guardrail_flags"].append(f"draft_failed:{type(e).__name__}")

    investigation_summary = None
    if confidence["band"] in config.get("investigation_trigger_bands", []):
        try:
            investigation_summary, investigation_usage = investigate_uncertain_message(
                client, message["text"], extraction, config,
            )
            usage.extend(investigation_usage)
        except anthropic.APIError as e:
            investigation_summary = None
            routing["guardrail_flags"].append(f"investigation_failed:{type(e).__name__}")

    return {
        "id": message["id"],
        "text": message["text"],
        "entry_channel": message.get("entry_channel"),
        "extraction": extraction,
        "confidence": confidence,
        "queue": routing["queue"],
        "loop_in": routing["loop_in"],
        "guardrail_flags": routing["guardrail_flags"],
        "review_priority": routing["review_priority"],
        "requires_human_review": routing["requires_human_review"],
        "health_expansion_flag": health_flag,
        "draft": draft_text,
        "draft_is_clarification_request": is_clarification,
        "investigation_summary": investigation_summary,
        "usage": usage,
    }

```

## `batch_runner.py`

```python
"""
Batch runner: executes the pipeline over the sample messages and writes
a timestamped results file plus aggregate cost/accuracy stats.

Re-run safety: the sample messages are read-only test fixtures, never
mutated here. Each run writes to a new timestamped file rather than
overwriting a fixed output, so a bad or partial run never destroys a
previous good one. Supports running the full set, a single split, or a
small subset of message IDs so iteration doesn't require a full re-run.
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from config import CONFIG
from pipeline import process_message

PROGRESS_PATH = Path(__file__).parent / "outputs" / "progress.json"

# Published per-million-token pricing for the models this pipeline uses.
# Pinned here (not fetched live) so cost figures are reproducible run to run.
PRICING = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
}

DATA_PATH = Path(__file__).parent / "data" / "sample_messages.json"
OUTPUTS_DIR = Path(__file__).parent / "outputs"


def load_messages(split=None, ids=None):
    with open(DATA_PATH) as f:
        messages = json.load(f)
    if ids:
        wanted = set(ids)
        messages = [m for m in messages if m["id"] in wanted]
    elif split and split != "all":
        messages = [m for m in messages if m["split"] == split]
    return messages


def compute_cost(usage_list):
    total = 0.0
    for u in usage_list:
        rates = PRICING[u["model"]]
        total += u["input_tokens"] / 1_000_000 * rates["input"]
        total += u["output_tokens"] / 1_000_000 * rates["output"]
    return total


def write_progress(current, total, started_at, last_message_id, status):
    elapsed = time.monotonic() - started_at
    avg_per_message = elapsed / current if current > 0 else None
    remaining = (
        avg_per_message * (total - current)
        if avg_per_message is not None and status == "running"
        else 0
    )
    PROGRESS_PATH.parent.mkdir(exist_ok=True)
    with open(PROGRESS_PATH, "w") as f:
        json.dump({
            "current": current,
            "total": total,
            "percent": round(current / total * 100, 1) if total else 0,
            "elapsed_seconds": round(elapsed, 1),
            "avg_seconds_per_message": round(avg_per_message, 2) if avg_per_message else None,
            "estimated_remaining_seconds": round(remaining, 1),
            "last_message_id": last_message_id,
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)


def run_batch(messages, client, config):
    results = []
    total = len(messages)
    started_at = time.monotonic()
    write_progress(0, total, started_at, None, "running")
    for i, msg in enumerate(messages, start=1):
        msg_started = time.monotonic()
        result = process_message(client, msg, config)
        result["latency_seconds"] = round(time.monotonic() - msg_started, 3)
        result["ground_truth_category"] = msg["ground_truth_category"]
        result["split"] = msg["split"]
        result["edge_case_type"] = msg.get("edge_case_type")
        result["expected_sensitive_topic"] = msg.get("sensitive_topic", False)
        result["expected_retention_risk_override"] = msg.get("retention_risk_override", False)
        result["cost"] = compute_cost(result.get("usage", []))
        results.append(result)
        write_progress(i, total, started_at, msg["id"], "running")
        print(f"  [{i}/{total}] {msg['id']} -> queue={result.get('queue')} confidence={result.get('confidence', {}).get('band')}")
    write_progress(total, total, started_at, messages[-1]["id"] if messages else None, "complete")
    return results


def compute_stats(results, categories):
    scored = [r for r in results if "extraction" in r]
    failed = [r for r in results if "extraction" not in r]

    confusion = {gt: {pred: 0 for pred in categories} for gt in categories}
    for r in scored:
        gt = r["ground_truth_category"]
        pred = r["extraction"]["category"]
        if gt in confusion and pred in confusion[gt]:
            confusion[gt][pred] += 1

    per_category = {}
    for cat in categories:
        tp = confusion[cat][cat] if cat in confusion else 0
        fn = sum(confusion[cat][p] for p in categories if p != cat) if cat in confusion else 0
        fp = sum(confusion[gt][cat] for gt in categories if gt != cat and cat in confusion.get(gt, {}))
        precision = tp / (tp + fp) if (tp + fp) > 0 else None
        recall = tp / (tp + fn) if (tp + fn) > 0 else None
        per_category[cat] = {"precision": precision, "recall": recall, "support": tp + fn}

    correct = sum(1 for r in scored if r["extraction"]["category"] == r["ground_truth_category"])
    overall_accuracy = correct / len(scored) if scored else None

    # Guardrail-specific accuracy: did we detect the signals the test data
    # was deliberately built to exercise (recall), and did we avoid flagging
    # ones that weren't supposed to be flagged (false positives/precision)?
    sensitive_cases = [r for r in scored if r["expected_sensitive_topic"]]
    sensitive_caught = sum(1 for r in sensitive_cases if r["extraction"]["sensitive_topic_flags"])
    sensitive_flagged_total = sum(1 for r in scored if r["extraction"]["sensitive_topic_flags"])
    sensitive_false_positives = sum(
        1 for r in scored if r["extraction"]["sensitive_topic_flags"] and not r["expected_sensitive_topic"]
    )

    retention_cases = [r for r in scored if r["expected_retention_risk_override"]]
    retention_caught = sum(1 for r in retention_cases if r["extraction"]["retention_risk_language"])
    retention_flagged_total = sum(1 for r in scored if r["extraction"]["retention_risk_language"])
    retention_false_positives = sum(
        1 for r in scored if r["extraction"]["retention_risk_language"] and not r["expected_retention_risk_override"]
    )

    confidence_bands = {"high": 0, "medium": 0, "low": 0}
    for r in scored:
        confidence_bands[r["confidence"]["band"]] += 1

    total_cost = sum(r["cost"] for r in results)

    latencies = sorted(r["latency_seconds"] for r in results if "latency_seconds" in r)
    investigated_latencies = sorted(
        r["latency_seconds"] for r in results if r.get("investigation_summary") and "latency_seconds" in r
    )

    def _percentile(values, pct):
        if not values:
            return None
        idx = min(len(values) - 1, int(len(values) * pct))
        return round(values[idx], 2)

    return {
        "n_total": len(results),
        "n_scored": len(scored),
        "n_failed": len(failed),
        "overall_accuracy": overall_accuracy,
        "confusion_matrix": confusion,
        "per_category": per_category,
        "confidence_band_counts": confidence_bands,
        "sensitive_topic_detection": {
            "expected": len(sensitive_cases),
            "caught": sensitive_caught,
            "total_flagged": sensitive_flagged_total,
            "false_positives": sensitive_false_positives,
        },
        "retention_risk_detection": {
            "expected": len(retention_cases),
            "caught": retention_caught,
            "total_flagged": retention_flagged_total,
            "false_positives": retention_false_positives,
        },
        "total_cost_usd": round(total_cost, 6),
        "latency_seconds": {
            "min": round(latencies[0], 2) if latencies else None,
            "median": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "max": round(latencies[-1], 2) if latencies else None,
            "median_when_investigated": _percentile(investigated_latencies, 0.5),
            "max_when_investigated": round(investigated_latencies[-1], 2) if investigated_latencies else None,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Run the AI message-routing pipeline over sample messages.")
    parser.add_argument("--split", choices=["dev", "held_out", "fresh_check", "success_mailbox", "all"], default="dev",
                         help="Which split to run (default: dev). Ignored if --ids is given.")
    parser.add_argument("--ids", nargs="+", help="Specific message IDs to run instead of a full split.")
    args = parser.parse_args()

    load_dotenv()
    # Explicit timeout + retry config rather than relying on SDK defaults -
    # 3 retries with exponential backoff on transient errors (rate limits,
    # 5xx, connection drops), 60s per-call timeout so a hung request can't
    # stall the whole batch. Real support volume runs async in the
    # background against whatever inbox the message already sits in (see
    # PIPELINE_REFERENCE.md), so a slow or failed call never blocks a
    # human from working the ticket manually in the meantime - it only
    # means the AI enrichment arrives late or not at all for that message,
    # and process_message() already degrades that to human review safely.
    client = anthropic.Anthropic(max_retries=3, timeout=60.0)

    messages = load_messages(split=args.split, ids=args.ids)
    if not messages:
        print("No messages matched the given split/ids.")
        return

    print(f"Running {len(messages)} message(s)...")
    results = run_batch(messages, client, CONFIG)
    stats = compute_stats(results, CONFIG["categories"])

    OUTPUTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = args.split if not args.ids else "custom"
    out_path = OUTPUTS_DIR / f"run_{timestamp}_{label}.json"
    with open(out_path, "w") as f:
        json.dump({"stats": stats, "results": results}, f, indent=2)

    print(f"\nWrote {out_path}")
    print(f"Scored: {stats['n_scored']}/{stats['n_total']} (failed: {stats['n_failed']})")
    print(f"Overall accuracy: {stats['overall_accuracy']}")
    print(f"Confidence bands: {stats['confidence_band_counts']}")
    print(f"Sensitive topic detection: {stats['sensitive_topic_detection']['caught']}/{stats['sensitive_topic_detection']['expected']} "
          f"(false positives: {stats['sensitive_topic_detection']['false_positives']}/{stats['sensitive_topic_detection']['total_flagged']} flagged)")
    print(f"Retention risk detection: {stats['retention_risk_detection']['caught']}/{stats['retention_risk_detection']['expected']} "
          f"(false positives: {stats['retention_risk_detection']['false_positives']}/{stats['retention_risk_detection']['total_flagged']} flagged)")
    print(f"Total cost: ${stats['total_cost_usd']}")
    lat = stats["latency_seconds"]
    print(f"Latency (seconds): min={lat['min']} median={lat['median']} p95={lat['p95']} max={lat['max']} "
          f"| when investigated: median={lat['median_when_investigated']} max={lat['max_when_investigated']}")
    return out_path


if __name__ == "__main__":
    main()

```

## `dashboard.py`

```python
"""
Generates a static, self-contained HTML dashboard from a batch_runner
results file - dark, card-based visual style (matching Dan's other
project dashboards), with filter pills by queue and expandable rows
showing the full extraction, confidence rubric, draft, and agentic
investigation trace per message. No server, no dependencies beyond the
standard library - just open the file in a browser.
"""

import argparse
import html
import json
from pathlib import Path

OUTPUTS_DIR = Path(__file__).parent / "outputs"

QUEUE_COLORS = {
    "Service": {"col": "#60a5fa", "bg": "#0b1e3f", "bdr": "#1e3a8a"},
    "Success": {"col": "#34d399", "bg": "#052e16", "bdr": "#065f46"},
    "Sales": {"col": "#c4b5fd", "bg": "#1e1533", "bdr": "#4c1d95"},
    "Team Lead Triage": {"col": "#fbbf24", "bg": "#2a1500", "bdr": "#7c2d12"},
}
BAND_COLORS = {
    "high": {"col": "#34d399", "bg": "#052e16", "bdr": "#065f46"},
    "medium": {"col": "#fbbf24", "bg": "#2a1500", "bdr": "#7c2d12"},
    "low": {"col": "#f87171", "bg": "#350a0a", "bdr": "#991b1b"},
}

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1117; color: #e2e8f0; padding: 24px; font-size: 13px; line-height: 1.5; }
h1 { font-size: 20px; font-weight: 600; color: #f8fafc; margin-bottom: 6px; }
.subtitle { font-size: 13px; color: #64748b; margin-bottom: 22px; }

.stats { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
.stat { background: #1a1d2e; border: 1px solid #2d3149; border-radius: 8px; padding: 10px 14px; text-align: center; min-width: 96px; flex: 1; }
.stat .sv { font-size: 18px; font-weight: 700; color: var(--col, #f8fafc); }
.stat .sl { font-size: 10px; color: #64748b; margin-top: 3px; }

.filter-bar { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 20px; padding: 12px 14px; background: #141628; border: 1px solid #2d3149; border-radius: 8px; }
.filter-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: #475569; margin-right: 4px; white-space: nowrap; }
.fbtn { padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 600; cursor: pointer; border: 1px solid #334155; background: #1a1d2e; color: #475569; transition: all 0.15s; }
.fbtn.active { background: var(--bg); border-color: var(--bdr); color: var(--col); }
.fbtn:hover { opacity: 0.85; }
.row-hint { font-size: 10px; color: #475569; margin-left: auto; white-space: nowrap; }

.divider { margin: 26px 0 10px; font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #475569; display: flex; align-items: center; gap: 8px; }
.divider::after { content: ''; flex: 1; height: 1px; background: #2d3148; }

.pipeline { display: flex; flex-direction: column; gap: 10px; }
.card { background: #1e2130; border: 1px solid #2d3148; border-radius: 10px; overflow: hidden; transition: border-color 0.2s; }
.card:hover { border-color: #4a5080; }
.card-summary { padding: 12px 16px; display: flex; align-items: flex-start; gap: 12px; cursor: pointer; }
.avatar { width: 32px; height: 32px; border-radius: 7px; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex-shrink: 0; background: var(--bg); color: var(--col); border: 1px solid var(--bdr); }
.card-body { flex: 1; min-width: 0; }
.card-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 5px; }
.msg-id { font-family: ui-monospace, monospace; color: #64748b; font-size: 11px; }
.msg-snip { font-size: 12px; color: #94a3b8; flex: 1; min-width: 160px; }
.header-right { display: flex; align-items: center; gap: 6px; margin-left: auto; flex-shrink: 0; }
.badge { font-size: 10px; font-weight: 600; padding: 3px 9px; border-radius: 20px; white-space: nowrap; background: var(--bg); color: var(--col); border: 1px solid var(--bdr); }
.badge-gray { background: rgba(107,114,128,0.15); color: #9ca3af; border: 1px solid #334155; }
.badge-mismatch { background: rgba(239,68,68,0.12); color: #fca5a5; border: 1px solid #7f1d1d; }
.tag { display: inline-block; font-size: 10px; padding: 2px 8px; border-radius: 10px; margin: 1px; background: rgba(148,163,184,0.1); color: #94a3b8; border: 1px solid #334155; }
.tag.flag { background: rgba(251,191,36,0.08); color: #fbbf24; border-color: #7c2d12; }
.gt-line { font-size: 11px; color: #64748b; }
.gt-line b { color: #cbd5e1; font-weight: 500; }

.detail { display: none; border-top: 1px solid #2d3148; padding: 18px 20px; background: #171924; }
.detail.open { display: block; }
.detail h3 { font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.07em; margin: 16px 0 8px; }
.detail h3:first-child { margin-top: 0; }
.detail p { font-size: 12px; color: #94a3b8; line-height: 1.6; margin-bottom: 6px; }
.dl { display: flex; gap: 8px; font-size: 12px; padding: 3px 0; }
.dl .k { color: #64748b; min-width: 130px; flex-shrink: 0; }
.dl .v { color: #cbd5e1; }
.rubric { font-family: ui-monospace, monospace; font-size: 11px; padding: 2px 0; }
.rubric.pos { color: #6ee7a0; }
.rubric.neg { color: #fb923c; }
.quote { background: #1e2130; border-left: 2px solid #3b82f6; border-radius: 4px; padding: 10px 14px; font-size: 12px; color: #cbd5e1; line-height: 1.6; margin: 4px 0 10px; }
.quote.agent { border-left-color: #a78bfa; }
.reasoning { font-style: italic; color: #64748b; font-size: 12px; }
"""


def stat_card(value, label, color=None):
    style = f' style="--col:{color}"' if color else ""
    return f'<div class="stat"{style}><div class="sv">{html.escape(str(value))}</div><div class="sl">{html.escape(label)}</div></div>'


def badge(text, colors=None, cls=""):
    if colors:
        style = f'style="--col:{colors["col"]};--bg:{colors["bg"]};--bdr:{colors["bdr"]}"'
        return f'<span class="badge {cls}" {style}>{html.escape(text)}</span>'
    return f'<span class="badge {cls}">{html.escape(text)}</span>'


def tags(items, flag=False):
    cls = "tag flag" if flag else "tag"
    return "".join(f'<span class="{cls}">{html.escape(str(t))}</span>' for t in items)


def rubric_html(reasons):
    rows = []
    for r in reasons:
        cls = "neg" if r.strip().startswith("-") else "pos"
        rows.append(f'<div class="rubric {cls}">{html.escape(r)}</div>')
    return "".join(rows)


def card_html(r, idx):
    queue = r.get("queue", "Unknown")
    qc = QUEUE_COLORS.get(queue, {"col": "#9ca3af", "bg": "#1a1d2e", "bdr": "#334155"})
    extraction = r.get("extraction", {})
    confidence = r.get("confidence", {"score": "-", "band": "low"})
    bc = BAND_COLORS.get(confidence.get("band", "low"), BAND_COLORS["low"])
    gt = r.get("ground_truth_category", "")
    pred = extraction.get("category", "N/A")
    mismatch = gt and pred and gt != pred
    urgent = r.get("review_priority") == "urgent"
    avatar_letter = queue[0] if queue else "?"

    snippet = r["text"][:90] + ("..." if len(r["text"]) > 90 else "")
    gt_line = f'<span class="gt-line">Ground truth <b>{html.escape(gt)}</b> &rarr; predicted <b>{html.escape(pred)}</b></span>' if gt else ""

    header_badges = [
        badge(f"{confidence.get('band','?')} ({confidence.get('score','?')})", bc),
        badge(queue, qc),
    ]
    if mismatch:
        header_badges.append(badge("mismatch", cls="badge-mismatch"))
    if urgent:
        header_badges.append(badge("urgent", cls="badge-mismatch"))

    summary = f"""
    <div class="card-summary" onclick="toggleCard({idx})">
      <div class="avatar" style="--col:{qc['col']};--bg:{qc['bg']};--bdr:{qc['bdr']}">{html.escape(avatar_letter)}</div>
      <div class="card-body">
        <div class="card-header">
          <span class="msg-id">{html.escape(r['id'])}</span>
          <span class="msg-snip">{html.escape(snippet)}</span>
          <div class="header-right">{''.join(header_badges)}</div>
        </div>
        {gt_line}
        <div style="margin-top:4px">{tags(r.get('loop_in', []))}{tags([r.get('entry_channel')] if r.get('entry_channel') else [])}</div>
      </div>
    </div>"""

    # Detail panel - full extraction, rubric, routing, draft, investigation
    reasoning = extraction.get("reasoning", "")
    extraction_rows = "".join(
        f'<div class="dl"><span class="k">{html.escape(k)}</span><span class="v">{html.escape(str(v))}</span></div>'
        for k, v in [
            ("Category alternatives", ", ".join(extraction.get("category_alternatives", [])) or "none"),
            ("Contradictory signals", extraction.get("contradictory_signals", False)),
            ("Account/order reference", extraction.get("account_or_order_reference") or "none"),
            ("Issue type", extraction.get("issue_type", "")),
            ("Sentiment / urgency", f"{extraction.get('sentiment','')} / {extraction.get('urgency','')}"),
            ("Expansion intent", extraction.get("expansion_intent_language", False)),
            ("Retention risk language", extraction.get("retention_risk_language", False)),
            ("Sensitive topic flags", ", ".join(extraction.get("sensitive_topic_flags", [])) or "none"),
            ("Entry channel", r.get("entry_channel") or "unknown"),
        ]
    )

    draft = r.get("draft")
    draft_block = f'<div class="quote">{html.escape(draft).replace(chr(10), "<br>")}</div>' if draft else '<p>No draft (extraction or draft call failed).</p>'

    investigation = r.get("investigation_summary")
    investigation_block = (
        f'<h3>Agent investigation (agentic - only runs on low confidence)</h3><div class="quote agent">{html.escape(investigation)}</div>'
        if investigation else ""
    )

    flags_block = tags(r.get("guardrail_flags", []), flag=True) or '<span class="tag">none</span>'
    cost = r.get("cost")
    cost_line = f"${cost:.6f}" if isinstance(cost, (int, float)) else "n/a"

    detail = f"""
    <div class="detail" id="detail-{idx}">
      <h3>Full message</h3>
      <p>{html.escape(r['text'])}</p>
      {f'<p class="reasoning">"{html.escape(reasoning)}"</p>' if reasoning else ''}

      <h3>Extraction</h3>
      {extraction_rows}

      <h3>Confidence rubric</h3>
      {rubric_html(confidence.get('reasons', []))}
      <div class="dl" style="margin-top:6px"><span class="k">Final score / band</span><span class="v">{confidence.get('score','?')} / {confidence.get('band','?')}</span></div>

      <h3>Routing</h3>
      <div class="dl"><span class="k">Queue</span><span class="v">{html.escape(queue)}</span></div>
      <div class="dl"><span class="k">Looped in</span><span class="v">{', '.join(r.get('loop_in', [])) or 'none'}</span></div>
      <div class="dl"><span class="k">Guardrail flags</span><span class="v">{flags_block}</span></div>
      <div class="dl"><span class="k">Cost (this message)</span><span class="v">{cost_line}</span></div>

      <h3>Draft reply</h3>
      {draft_block}
      {investigation_block}
    </div>"""

    return summary + detail


def card_wrapper(r, idx):
    queue = r.get("queue", "Unknown")
    urgent = r.get("review_priority") == "urgent"
    return f'<div class="card" data-queue="{html.escape(queue)}" data-urgent="{"1" if urgent else "0"}">{card_html(r, idx)}</div>'


def build_dashboard(data, source_label):
    stats = data["stats"]
    results = [r for r in data["results"] if "extraction" in r]

    queues_present = ["Service", "Success", "Sales", "Team Lead Triage"]
    n_by_queue = {q: sum(1 for r in results if r.get("queue") == q) for q in queues_present}
    n_urgent = sum(1 for r in results if r.get("review_priority") == "urgent")

    accuracy = stats.get("overall_accuracy")
    accuracy_str = f"{round(accuracy * 100, 1)}%" if accuracy is not None else "N/A"
    sens = stats["sensitive_topic_detection"]
    reten = stats["retention_risk_detection"]

    stat_cards = "".join([
        stat_card(f"{stats['n_scored']}/{stats['n_total']}", "scored / total"),
        stat_card(accuracy_str, "accuracy", "#34d399"),
        stat_card(f"${stats['total_cost_usd']:.3f}", "total cost", "#60a5fa"),
        stat_card(f"H:{stats['confidence_band_counts']['high']} M:{stats['confidence_band_counts']['medium']} L:{stats['confidence_band_counts']['low']}", "confidence bands"),
        stat_card(f"{sens['caught']}/{sens['expected']}", "sensitive-topic recall", "#34d399" if sens['false_positives'] == 0 else "#fbbf24"),
        stat_card(f"{sens['false_positives']}/{sens['total_flagged']}", "sensitive false positives", "#f87171" if sens['false_positives'] else "#34d399"),
        stat_card(f"{reten['caught']}/{reten['expected']}", "retention-risk recall", "#34d399"),
        stat_card(n_by_queue.get("Team Lead Triage", 0), "manager triage", "#fbbf24"),
        stat_card(n_urgent, "urgent review", "#f87171"),
    ])

    filter_defs = [
        ("all", "All", "#e2e8f0", "#1a1d2e", "#334155"),
        ("Service", "Service", QUEUE_COLORS["Service"]["col"], QUEUE_COLORS["Service"]["bg"], QUEUE_COLORS["Service"]["bdr"]),
        ("Success", "Success", QUEUE_COLORS["Success"]["col"], QUEUE_COLORS["Success"]["bg"], QUEUE_COLORS["Success"]["bdr"]),
        ("Sales", "Sales", QUEUE_COLORS["Sales"]["col"], QUEUE_COLORS["Sales"]["bg"], QUEUE_COLORS["Sales"]["bdr"]),
        ("Team Lead Triage", "Team Lead triage", QUEUE_COLORS["Team Lead Triage"]["col"], QUEUE_COLORS["Team Lead Triage"]["bg"], QUEUE_COLORS["Team Lead Triage"]["bdr"]),
        ("urgent", "Urgent only", "#f87171", "#350a0a", "#991b1b"),
    ]
    filter_html = "".join(
        f'<button class="fbtn{"" if cat == "urgent" else " active"}" data-cat="{cat}" style="--col:{col};--bg:{bg};--bdr:{bdr}" onclick="toggleFilter(this)">{label}</button>'
        for cat, label, col, bg, bdr in filter_defs
    )

    cards_html = "".join(card_wrapper(r, i) for i, r in enumerate(results))

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex, nofollow">
<title>AI Triage - Routing Results</title>
<style>{CSS}</style>
</head>
<body>
<h1>AI triage - routing results</h1>
<p class="subtitle">Source: {html.escape(source_label)} &middot; click any row to expand full reasoning, draft, and confidence rubric</p>

<div class="stats">{stat_cards}</div>

<div class="filter-bar">
  <span class="filter-label">Show</span>
  {filter_html}
  <span class="row-hint" id="row-hint"></span>
</div>

<div class="pipeline" id="pipeline">
{cards_html}
</div>

<script>
function toggleCard(idx) {{
  var d = document.getElementById('detail-' + idx);
  d.classList.toggle('open');
}}
(function() {{
  var btns = document.querySelectorAll('.fbtn');
  var queueBtns = document.querySelectorAll('.fbtn[data-cat]:not([data-cat="all"]):not([data-cat="urgent"])');
  var urgentBtn = document.querySelector('.fbtn[data-cat="urgent"]');

  window.toggleFilter = function(btn) {{
    var cat = btn.dataset.cat;
    if (cat === 'all') {{
      queueBtns.forEach(function(b) {{ b.classList.add('active'); }});
      urgentBtn.classList.remove('active');
    }} else {{
      btn.classList.toggle('active');
    }}
    applyFilters();
  }};

  function applyFilters() {{
    var activeQueues = [];
    var urgentOnly = false;
    btns.forEach(function(b) {{
      if (b.classList.contains('active')) {{
        if (b.dataset.cat === 'urgent') urgentOnly = true;
        else if (b.dataset.cat !== 'all') activeQueues.push(b.dataset.cat);
      }}
    }});
    var cards = document.querySelectorAll('#pipeline .card');
    var shown = 0;
    cards.forEach(function(c) {{
      var matchQueue = activeQueues.length === 0 || activeQueues.indexOf(c.dataset.queue) !== -1;
      var matchUrgent = !urgentOnly || c.dataset.urgent === '1';
      var visible = matchQueue && matchUrgent;
      c.style.display = visible ? '' : 'none';
      if (visible) shown++;
    }});
    document.getElementById('row-hint').textContent = shown + ' of ' + cards.length + ' shown';
  }}
  applyFilters();
}})();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Build an HTML dashboard from a batch_runner results file.")
    parser.add_argument("results_file", nargs="?", help="Path to a run_*.json file. Defaults to the most recent one in outputs/.")
    args = parser.parse_args()

    if args.results_file:
        results_path = Path(args.results_file)
    else:
        candidates = sorted(OUTPUTS_DIR.glob("run_*.json"))
        if not candidates:
            print("No run_*.json files found in outputs/. Run batch_runner.py first.")
            return
        results_path = candidates[-1]

    with open(results_path) as f:
        data = json.load(f)

    html_content = build_dashboard(data, source_label=results_path.name)
    out_path = results_path.with_suffix(".html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Wrote {out_path}")
    return out_path


if __name__ == "__main__":
    main()

```

## `opus_comparison.py`

```python
"""
One-off comparison: does claude-opus-4-8 out-perform the claude-haiku-4-5
baseline on the hardest slice of the message set - the 25 deliberately
ambiguous/edge-case messages in the dev split?

Held-out edge cases (5 messages) are deliberately excluded here, same as
every other exploratory run in this project: the held-out split is run
once, near the very end, for final validation - not used to compare
models or tune thresholds along the way.

This is a real, API-tested comparison (not simulated) using the exact
same classify_and_extract prompt and score_confidence rubric as the main
pipeline - only the model string changes. The Haiku side is not
re-run; it's read from the last validated full dev-set run
(outputs/run_20260704T222727Z_dev.json), since nothing in
classify_and_extract has changed since that run (only draft_response/
determine_queue have) - so re-spending API cost to reproduce it would
add nothing.
"""

import copy
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from config import CONFIG
from pipeline import classify_and_extract, score_confidence

DATA_PATH = Path(__file__).parent / "data" / "sample_messages.json"
BASELINE_RUN_PATH = Path(__file__).parent / "outputs" / "run_20260704T222727Z_dev.json"
OUTPUTS_DIR = Path(__file__).parent / "outputs"

PRICING = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
}


def compute_cost(usage):
    rates = PRICING[usage["model"]]
    return usage["input_tokens"] / 1_000_000 * rates["input"] + usage["output_tokens"] / 1_000_000 * rates["output"]


def load_edge_case_messages():
    with open(DATA_PATH, encoding="utf-8") as f:
        messages = json.load(f)
    return [m for m in messages if m.get("edge_case_type") and m["split"] == "dev"]


def load_haiku_baseline(message_ids):
    with open(BASELINE_RUN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    by_id = {r["id"]: r for r in data["results"] if "extraction" in r}
    return {mid: by_id[mid] for mid in message_ids if mid in by_id}


def main():
    load_dotenv()
    client = anthropic.Anthropic(max_retries=3, timeout=60.0)

    messages = load_edge_case_messages()
    message_ids = [m["id"] for m in messages]
    haiku_baseline = load_haiku_baseline(message_ids)
    missing = set(message_ids) - set(haiku_baseline)
    if missing:
        print(f"Warning: {len(missing)} message(s) not found in baseline run, skipping: {missing}")
        messages = [m for m in messages if m["id"] not in missing]

    opus_config = copy.deepcopy(CONFIG)
    opus_config["models"]["classify_extract"] = "claude-opus-4-8"

    print(f"Running {len(messages)} dev-split edge-case message(s) through claude-opus-4-8...")
    rows = []
    total_opus_cost = 0.0
    for i, msg in enumerate(messages, start=1):
        extraction, usage = classify_and_extract(
            client, msg["text"], opus_config, entry_channel=msg.get("entry_channel"),
        )
        confidence = score_confidence(extraction, opus_config)
        cost = compute_cost(usage)
        total_opus_cost += cost

        haiku_r = haiku_baseline[msg["id"]]
        row = {
            "id": msg["id"],
            "edge_case_type": msg["edge_case_type"],
            "ground_truth_category": msg["ground_truth_category"],
            "haiku_category": haiku_r["extraction"]["category"],
            "haiku_confidence": haiku_r["confidence"]["score"],
            "haiku_correct": haiku_r["extraction"]["category"] == msg["ground_truth_category"],
            "opus_category": extraction["category"],
            "opus_confidence": confidence["score"],
            "opus_correct": extraction["category"] == msg["ground_truth_category"],
            "opus_cost_usd": round(cost, 6),
            "agree": haiku_r["extraction"]["category"] == extraction["category"],
        }
        rows.append(row)
        print(f"  [{i}/{len(messages)}] {msg['id']} ({msg['edge_case_type']}): "
              f"haiku={row['haiku_category']}({row['haiku_confidence']}) "
              f"opus={row['opus_category']}({row['opus_confidence']}) "
              f"gt={msg['ground_truth_category']}")

    n = len(rows)
    haiku_accuracy = sum(r["haiku_correct"] for r in rows) / n
    opus_accuracy = sum(r["opus_correct"] for r in rows) / n
    agreement = sum(r["agree"] for r in rows) / n
    haiku_avg_conf = sum(r["haiku_confidence"] for r in rows) / n
    opus_avg_conf = sum(r["opus_confidence"] for r in rows) / n
    disagreements = [r for r in rows if not r["agree"]]

    summary = {
        "n_messages": n,
        "haiku_accuracy": round(haiku_accuracy, 4),
        "opus_accuracy": round(opus_accuracy, 4),
        "agreement_rate": round(agreement, 4),
        "haiku_avg_confidence": round(haiku_avg_conf, 2),
        "opus_avg_confidence": round(opus_avg_conf, 2),
        "total_opus_cost_usd": round(total_opus_cost, 6),
        "avg_opus_cost_per_message_usd": round(total_opus_cost / n, 6),
        "n_disagreements": len(disagreements),
    }

    print("\n--- Summary ---")
    for k, v in summary.items():
        print(f"{k}: {v}")
    if disagreements:
        print("\nDisagreements (haiku vs opus):")
        for r in disagreements:
            print(f"  {r['id']} ({r['edge_case_type']}): gt={r['ground_truth_category']} "
                  f"haiku={r['haiku_category']} opus={r['opus_category']}")

    OUTPUTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUTS_DIR / f"opus_comparison_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, indent=2)
    print(f"\nWrote {out_path}")
    return out_path


if __name__ == "__main__":
    main()

```

## `preview_server.py`

```python
"""
A restricted static file server for previewing progress.html and the
outputs/ dashboard files during this build - deliberately narrower than
`python -m http.server`, which would happily serve (and list) .env,
.git, and __pycache__ from the project root.

Blocks serving and directory-listing of anything under .env, .git, or
__pycache__. Everything else in the project folder is served normally.
"""

import http.server
import os
import sys

PORT = 8756
ROOT = os.path.dirname(os.path.abspath(__file__))

BLOCKED_NAMES = {".env", ".git", "__pycache__"}


def is_blocked(url_path):
    path = url_path.split("?")[0].lstrip("/")
    parts = [p for p in path.split("/") if p]
    return any(p in BLOCKED_NAMES or p.startswith(".env.") for p in parts)


class RestrictedHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        if is_blocked(self.path):
            self.send_error(403, "Forbidden")
            return
        super().do_GET()

    def do_HEAD(self):
        if is_blocked(self.path):
            self.send_error(403, "Forbidden")
            return
        super().do_HEAD()

    def list_directory(self, path):
        # Filter blocked names out of directory listings entirely so
        # they don't even show up as (403'd) links.
        try:
            entries = os.listdir(path)
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None
        filtered = [e for e in entries if e not in BLOCKED_NAMES]
        original_listdir = os.listdir
        os.listdir = lambda p: filtered
        try:
            return super().list_directory(path)
        finally:
            os.listdir = original_listdir


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    # ThreadingHTTPServer, not the plain single-threaded HTTPServer - a
    # single slow/kept-alive connection would otherwise block every
    # other request (including the progress.html polling loop).
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), RestrictedHandler) as httpd:
        print(f"Serving {ROOT} on http://127.0.0.1:{port} (.env / .git / __pycache__ blocked)")
        httpd.serve_forever()

```

## `data/brand_guidelines.json`

```json
{
  "_note": "ILLUSTRATIVE PLACEHOLDER - not any real company's actual brand guidelines. Stands in for what would, in production, be a live query against wherever the real company's actual brand guide is hosted (e.g. a Frontify-style brand platform). Read fresh at draft time, not baked into pipeline code, so updating this file changes every subsequent draft without touching pipeline.py.",
  "tone": "Warm, clear, and competent. Acknowledge frustration before addressing the issue. Never robotic, never overly casual.",
  "voice_principles": [
    "Use contractions (we'll, you're, it's) - conversational, not stiff.",
    "Active voice, verb first.",
    "Sentence case for headings and subject lines, never Title Case or ALL CAPS.",
    "No exclamation marks in routine replies - reserve enthusiasm for real good news (e.g. a resolved issue).",
    "Say what happened and what happens next, in that order."
  ],
  "banned_words_or_phrases": [
    "unfortunately",
    "as per",
    "kindly",
    "please note that",
    "I apologize for any inconvenience this may have caused",
    "per our policy",
    "at your earliest convenience"
  ],
  "avoid_ai_isms": {
    "_purpose": "Words and patterns that make a reply read as AI-generated rather than written by a person - a distinct category from general corporate-speak above.",
    "banned_words": [
      "genuine", "genuinely",
      "delve", "delve into",
      "rest assured",
      "utilize", "leverage",
      "robust", "seamless",
      "navigate this",
      "moving forward",
      "certainly!", "absolutely!"
    ],
    "banned_phrases": [
      "I understand your frustration",
      "I completely understand",
      "please don't hesitate to reach out",
      "I hope this helps",
      "it's important to note that",
      "it's worth noting that",
      "in conclusion", "to summarize"
    ],
    "style_rules": [
      "Do not stack em dashes as a stylistic tic - use a period or comma instead.",
      "Acknowledge frustration in your own words tied to the specific situation, never with a stock empathy phrase.",
      "No reflexive filler affirmations before getting to the point."
    ]
  },
  "preferred_phrases": {
    "greeting": "Hi [Name],",
    "sign_off": "Best,\nThe Example Co. Team",
    "acknowledging_delay": "Thanks for flagging this - here's what's happening and what we're doing about it.",
    "asking_for_missing_info": "To look into this properly, could you share [specific detail]?"
  },
  "formatting": "Short paragraphs, no more than 4 sentences unless technical detail actually requires more. One clear ask per message if information is missing.",
  "brand_name_usage": "Always 'Example Co.', never other casings or spacing variants."
}

```

## `data/mock_backend.json`

```json
{
  "_note": "SYNTHETIC TEST DATA ONLY - stands in for what would, in a real deployment, be live calls to Example Co.'s own MCP server (tracking/rates/duty/label tools, already shipped) plus their CRM/billing system for account context. See the build plan's 'Test system vs. real system' table for the full mapping.",
  "orders": {
    "ORD-88213": {
      "status": "in_transit",
      "last_scan": "9 days ago",
      "carrier": "DHL",
      "destination_country": "Germany",
      "note": "Tracking has not updated since the last scan - matches the customer's complaint."
    },
    "ORD-50219": {
      "status": "held_in_customs",
      "last_scan": "14 days ago",
      "carrier": "FedEx",
      "destination_country": "France",
      "note": "Customs hold, reason code pending - no commercial invoice on file for this shipment."
    },
    "ORD-60771": {
      "status": "delivered",
      "last_scan": "3 days ago",
      "carrier": "UPS",
      "destination_country": "United States",
      "note": "Delivered at correct weight; billed weight on file is higher than the shipped weight - matches the customer's overcharge claim."
    }
  },
  "accounts": {
    "ORD-88213": {
      "plan_tier": "Plus",
      "account_age_months": 14,
      "prior_tickets_last_90_days": 1,
      "arr_band": "under_5k"
    },
    "ORD-50219": {
      "plan_tier": "Scale",
      "account_age_months": 31,
      "prior_tickets_last_90_days": 4,
      "arr_band": "5k_to_25k"
    },
    "ORD-60771": {
      "plan_tier": "Premier",
      "account_age_months": 8,
      "prior_tickets_last_90_days": 0,
      "arr_band": "under_5k"
    }
  }
}

```

## Sample data (excerpt)

The full test set is 120 messages (100 dev / 20 held-out), each with a
ground-truth category label, entry channel, and edge-case metadata
where relevant. Reproduced here is a short excerpt to show the schema;
the complete file lives at `data/sample_messages.json` in the repo.

```json
[
  {
    "id": "msg_001",
    "text": "Hi, I need to know the correct HS code for exporting bluetooth headphones to Germany. My last shipment got held at customs because the code I used was apparently wrong.",
    "ground_truth_category": "Service",
    "split": "dev",
    "edge_case_type": null,
    "sensitive_topic": false,
    "retention_risk_override": false,
    "entry_channel": "Support"
  },
  {
    "id": "msg_002",
    "text": "My order #ORD-88213 has been stuck on 'in transit' for 9 days with no tracking updates. Customer is asking me where it is and I don't know what to tell them.",
    "ground_truth_category": "Service",
    "split": "dev",
    "edge_case_type": null,
    "sensitive_topic": false,
    "retention_risk_override": false,
    "entry_channel": "Support"
  },
  {
    "id": "msg_003",
    "text": "The shipping label I printed this morning has the wrong dimensions on it - it printed at 4x6 when I selected 6x4. Can you help me reprint it correctly?",
    "ground_truth_category": "Service",
    "split": "dev",
    "edge_case_type": null,
    "sensitive_topic": false,
    "retention_risk_override": false,
    "entry_channel": "Support"
  }
]
```
