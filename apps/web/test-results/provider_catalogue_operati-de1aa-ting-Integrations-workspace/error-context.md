# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: provider_catalogue_operations.spec.ts >> reviewed provider cards operate inside the existing Integrations workspace
- Location: tests/e2e/provider_catalogue_operations.spec.ts:5:5

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByRole('complementary', { name: 'Safe activation checklist' }).getByRole('button', { name: 'Open Integrations workspace' })

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - banner [ref=e2]:
    - link "TraderX" [ref=e3] [cursor=pointer]:
      - /url: /
    - navigation "Primary navigation" [ref=e4]:
      - link "Command Center" [ref=e5] [cursor=pointer]:
        - /url: /command-center
      - button "Log out" [ref=e6] [cursor=pointer]
  - main [ref=e7]:
    - region "Command Center" [ref=e8]:
      - generic [ref=e9]:
        - generic [ref=e10]:
          - paragraph [ref=e11]: Authenticated control plane
          - heading "Command Center" [level=1] [ref=e12]
          - paragraph [ref=e13]: Decision support only. TraderX cannot submit, modify, or close an order.
        - generic [ref=e14]:
          - generic [ref=e15]: Risk state
          - strong [ref=e16]: NORMAL
          - generic [ref=e17]: 2 of 2 position slots available
      - generic [ref=e18]:
        - complementary [ref=e19]:
          - paragraph [ref=e20]: Activation progress
          - heading "Safe activation checklist" [level=2] [ref=e21]
          - list [ref=e22]:
            - listitem [ref=e23]:
              - generic [ref=e24]: ✓
              - button "Open Initial setup workspace" [ref=e25] [cursor=pointer]:
                - strong [ref=e26]: Initial setup
                - generic [ref=e27]: Done
            - listitem [ref=e28]:
              - generic [ref=e29]: ✓
              - button "Open Account identity workspace" [ref=e30] [cursor=pointer]:
                - strong [ref=e31]: Account identity
                - generic [ref=e32]: Done
            - listitem [ref=e33]:
              - generic [ref=e34]: ✓
              - button "Open External loss rules workspace" [ref=e35] [cursor=pointer]:
                - strong [ref=e36]: External loss rules
                - generic [ref=e37]: Done
            - listitem [ref=e38]:
              - generic [ref=e39]: ✓
              - button "Open Internal guardrails workspace" [ref=e40] [cursor=pointer]:
                - strong [ref=e41]: Internal guardrails
                - generic [ref=e42]: Done
            - listitem [ref=e43]:
              - generic [ref=e44]: ✓
              - button "Open Verified account data workspace" [ref=e45] [cursor=pointer]:
                - strong [ref=e46]: Verified account data
                - generic [ref=e47]: Done
            - listitem [ref=e48]:
              - generic [ref=e49]: ○
              - button "Open CME Group connection workspace" [ref=e50] [cursor=pointer]:
                - strong [ref=e51]: CME Group connection
                - generic [ref=e52]: Required · not connected
            - listitem [ref=e53]:
              - generic [ref=e54]: ○
              - button "Open Cboe FX Spot connection workspace" [ref=e55] [cursor=pointer]:
                - strong [ref=e56]: Cboe FX Spot connection
                - generic [ref=e57]: Optional · not connected
            - listitem [ref=e58]:
              - generic [ref=e59]: ○
              - button "Open Coinbase Exchange connection workspace" [ref=e60] [cursor=pointer]:
                - strong [ref=e61]: Coinbase Exchange connection
                - generic [ref=e62]: Required · not connected
            - listitem [ref=e63]:
              - generic [ref=e64]: ✓
              - button "Open LiteLLM Gateway connection workspace" [ref=e65] [cursor=pointer]:
                - strong [ref=e66]: LiteLLM Gateway connection
                - generic [ref=e67]: Optional · done
            - listitem [ref=e68]:
              - generic [ref=e69]: ○
              - button "Open Active market selection workspace" [ref=e70] [cursor=pointer]:
                - strong [ref=e71]: Active market selection
                - generic [ref=e72]: Required for Strategies · not ready
            - listitem [ref=e73]:
              - generic [ref=e74]: ○
              - button "Open Validated strategy workspace" [ref=e75] [cursor=pointer]:
                - strong [ref=e76]: Validated strategy
                - generic [ref=e77]: Required for Paper trading · not ready
            - listitem [ref=e78]:
              - generic [ref=e79]: ○
              - button "Open Paper-trading evidence workspace" [ref=e80] [cursor=pointer]:
                - strong [ref=e81]: Paper-trading evidence
                - generic [ref=e82]: Required for live approval · not ready
            - listitem [ref=e83]:
              - generic [ref=e84]: ○
              - button "Open Live-approved strategy workspace" [ref=e85] [cursor=pointer]:
                - strong [ref=e86]: Live-approved strategy
                - generic [ref=e87]: Required for Opportunities · not ready
            - listitem [ref=e88]:
              - generic [ref=e89]: ○
              - button "Open Open broker position workspace" [ref=e90] [cursor=pointer]:
                - strong [ref=e91]: Open broker position
                - generic [ref=e92]: Optional for Trade monitoring · not ready
        - generic [ref=e93]:
          - region [ref=e94]:
            - generic [ref=e95]:
              - paragraph [ref=e96]: Recommendation gate
              - heading "Risk controls are active" [level=2] [ref=e97]
              - paragraph [ref=e98]: No blocking reason is recorded.
            - paragraph [ref=e99]: TraderX fails closed whenever account, position, price, or risk evidence is incomplete.
          - region "Account risk summary" [ref=e100]:
            - article [ref=e101]:
              - generic [ref=e102]: Account
              - strong [ref=e103]: Primary demo
              - generic [ref=e104]: DEMO · USD
            - article [ref=e105]:
              - generic [ref=e106]: Equity
              - strong [ref=e107]: "100000"
              - generic [ref=e108]: Balance 100000
            - article [ref=e109]:
              - generic [ref=e110]: Loss margins
              - strong [ref=e111]: "2000"
              - generic [ref=e112]: Daily margin · overall 5000
            - article [ref=e113]:
              - generic [ref=e114]: Open risk
              - strong [ref=e115]: "0"
              - generic [ref=e116]: "Data quality: VERIFIED"
          - region "Current TraderX evidence" [ref=e117]:
            - article [ref=e118]:
              - generic [ref=e119]: Active markets
              - strong [ref=e120]: 0 / 3
              - generic [ref=e121]: No market has been approved
            - article [ref=e122]:
              - generic [ref=e123]: Opportunities
              - strong [ref=e124]: "0"
              - generic [ref=e125]: No current opportunity evidence
            - article [ref=e126]:
              - generic [ref=e127]: Critical alerts
              - strong [ref=e128]: "0"
              - generic [ref=e129]: No critical alert recorded
            - article [ref=e130]:
              - generic [ref=e131]: Integration health
              - strong [ref=e132]: "0"
              - generic [ref=e133]: No account connection recorded
          - region [ref=e134]:
            - generic [ref=e136]:
              - paragraph [ref=e137]: TraderX workspace
              - heading "Markets" [level=2] [ref=e138]
              - paragraph [ref=e139]: Research and explicitly approve eligible active markets.
            - navigation "TraderX workspaces" [ref=e140]:
              - button "Integrations" [ref=e141] [cursor=pointer]
              - button "Account & risk" [ref=e142] [cursor=pointer]
              - button "Markets" [pressed] [ref=e143] [cursor=pointer]
              - button "Strategies" [ref=e144] [cursor=pointer]
              - button "Paper trading" [ref=e145] [cursor=pointer]
              - button "Opportunities" [ref=e146] [cursor=pointer]
              - button "Trade monitoring" [ref=e147] [cursor=pointer]
              - button "Journal" [ref=e148] [cursor=pointer]
              - button "Operations" [ref=e149] [cursor=pointer]
            - generic [ref=e151]:
              - region [ref=e152]:
                - paragraph [ref=e153]: Browser-independent schedule
                - heading "Market research automation" [level=3] [ref=e154]
                - paragraph [ref=e155]: One database-owned occurrence coordinates Commodity, Forex, and Cryptocurrency. The LLM explains evidence only; deterministic gates and ranking retain authority.
                - generic [ref=e156]:
                  - generic [ref=e157]:
                    - text: AI provider
                    - combobox "AI provider" [ref=e158]:
                      - option "LiteLLM Gateway" [selected]
                  - generic [ref=e159]:
                    - text: Model ID
                    - textbox "Model ID" [ref=e160]:
                      - /placeholder: Configured LiteLLM model alias
                  - paragraph [ref=e161]: LiteLLM Gateway is the advisory-model connection. Enter one of its configured model aliases (for example, provider/model). The exact ID is pinned to future runs; unsupported models fail advisory analysis without changing deterministic research results.
                  - generic [ref=e162]:
                    - text: Research interval
                    - spinbutton "Research interval" [ref=e163]: "86400"
                  - generic [ref=e164]:
                    - text: Anchor start
                    - textbox "Anchor start" [ref=e165]
                  - generic [ref=e166]:
                    - text: Account time zone
                    - textbox "Account time zone" [ref=e167]: Africa/Kigali
                  - generic [ref=e168]:
                    - checkbox "Enable recurring research" [ref=e169]
                    - text: Enable recurring research
                  - generic [ref=e170]:
                    - text: Reason for research settings
                    - textbox "Reason for research settings" [ref=e171]
                  - generic [ref=e172]:
                    - button "Save research settings" [disabled] [ref=e173]
                    - button "Run all three categories" [ref=e174] [cursor=pointer]
                - generic [ref=e175]:
                  - generic [ref=e176]:
                    - term [ref=e177]: Next occurrence
                    - definition [ref=e178]: Not scheduled
                  - generic [ref=e179]:
                    - term [ref=e180]: Last occurrence
                    - definition [ref=e181]: Not run
                  - generic [ref=e182]:
                    - term [ref=e183]: Overlap policy
                    - definition [ref=e184]: Skip; no catch-up
                - region [ref=e185]:
                  - heading "Coordinated run history" [level=4] [ref=e186]
                  - paragraph [ref=e187]: No coordinated market-research run has been recorded yet.
              - region [ref=e188]:
                - paragraph [ref=e189]: Active universe
                - heading "Research one governed market category" [level=3] [ref=e190]
                - paragraph [ref=e191]: Broker and data gates are evaluated before volatility and suitability ranking. Research never changes an active market.
                - group "Market category" [ref=e192]:
                  - button "Commodity" [ref=e193] [cursor=pointer]
                  - button "Forex" [pressed] [ref=e194] [cursor=pointer]
                  - button "Cryptocurrency" [ref=e195] [cursor=pointer]
                - button "Run Forex research" [ref=e196] [cursor=pointer]
              - region [ref=e197]:
                - heading "Human-approved active markets" [level=3] [ref=e198]
                - paragraph [ref=e199]: Exactly one slot per category. A new ranking never replaces a selection silently.
                - generic [ref=e200]:
                  - article [ref=e201]:
                    - generic [ref=e202]: commodity
                    - strong [ref=e203]: Inactive
                    - generic [ref=e204]: Awaiting an eligible human-approved selection
                  - article [ref=e205]:
                    - generic [ref=e206]: forex
                    - strong [ref=e207]: Inactive
                    - generic [ref=e208]: Awaiting an eligible human-approved selection
                  - article [ref=e209]:
                    - generic [ref=e210]: Cryptocurrency
                    - strong [ref=e211]: Inactive
                    - generic [ref=e212]: Awaiting an eligible human-approved selection
              - region [ref=e213]:
                - heading "Instrument Library" [level=3] [ref=e214]
                - paragraph [ref=e215]: Broker-supported instruments and their research-data readiness. A library record is never a live-market activation.
                - generic "Instrument counts" [ref=e216]:
                  - strong [ref=e217]: 1 broker instruments
                  - generic [ref=e218]: 1 data verified
                  - generic [ref=e219]: 1 shown
                - generic [ref=e220]:
                  - generic [ref=e221]:
                    - text: Find instrument
                    - searchbox "Find instrument" [ref=e222]
                  - generic [ref=e223]:
                    - text: Lifecycle
                    - combobox "Lifecycle" [ref=e224]:
                      - option "All states" [selected]
                      - option "Active"
                      - option "Inactive"
                      - option "Quarantined"
                  - generic [ref=e225]:
                    - text: Data
                    - combobox "Data" [ref=e226]:
                      - option "All data" [selected]
                      - option "Verified"
                      - option "Insufficient"
                      - option "Quarantined"
                - table "Instrument Library" [ref=e227]:
                  - row [ref=e228]:
                    - columnheader "Instrument" [ref=e229]
                    - columnheader "Category" [ref=e230]
                    - columnheader "Data" [ref=e231]
                    - columnheader "State and history" [ref=e232]
                  - row [ref=e233]:
                    - cell "EURUSD FOREX candidate" [ref=e234]:
                      - strong [ref=e235]: EURUSD
                      - generic [ref=e236]: FOREX candidate
                    - cell "FOREX" [ref=e237]
                    - cell [ref=e238]:
                      - strong [ref=e239]: VERIFIED
                      - text: No failed quality gates
                    - cell [ref=e240]:
                      - strong [ref=e241]: INACTIVE
                      - group [ref=e242]:
                        - generic "Evidence history" [ref=e243] [cursor=pointer]
                      - group [ref=e244]:
                        - generic "Approve specialist symbol mapping" [ref=e245] [cursor=pointer]
                        - option "Select provider" [selected]
                        - option "CBOE_FX_SPOT" [selected]
              - region [ref=e246]:
                - heading "Market replacement review" [level=3] [ref=e247]
                - paragraph [ref=e248]: Periodic comparison is advisory only. Use the category research and explicit approval form above to replace an active assignment.
                - paragraph [ref=e249]: No materially better eligible candidate is available for a current active slot.
              - region [ref=e250]:
                - heading "Retained knowledge and reactivation" [level=3] [ref=e251]
                - paragraph [ref=e252]: Inspect prior evidence, data gaps, and selective validation needs. Every path ends in human market approval.
                - generic [ref=e253]:
                  - generic [ref=e254]:
                    - text: Instrument
                    - combobox "Instrument" [ref=e255]:
                      - option "Select an instrument"
                      - option "XAUUSD · COMMODITY · INACTIVE" [selected]
                      - option "EURUSD · FOREX · INACTIVE"
                      - option "BTCUSD · CRYPTO · INACTIVE"
                  - button "Inspect retained knowledge" [ref=e256] [cursor=pointer]
                  - button "Create governed plan" [disabled] [ref=e257]
  - button "Open Next.js Dev Tools" [ref=e265]
  - alert [ref=e269]
```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | 
  3  | import { mockReadyCommandCenter } from "./support";
  4  | 
  5  | test("reviewed provider cards operate inside the existing Integrations workspace", async ({ page }) => {
  6  |   await mockReadyCommandCenter(page, { seedMarketAutomation: true });
  7  |   await page.goto("/command-center");
  8  |   await expect(page.getByRole("complementary", { name: "Safe activation checklist" }).getByText("LiteLLM Gateway connection")).toBeVisible();
  9  |   await expect(page.getByRole("complementary", { name: "Safe activation checklist" }).getByText("Optional · done")).toBeVisible();
  10 |   const checklist = page.getByRole("complementary", { name: "Safe activation checklist" });
> 11 |   await checklist.getByRole("button", { name: "Open Integrations workspace" }).click();
     |                                                                                ^ Error: locator.click: Test timeout of 30000ms exceeded.
  12 | 
  13 |   await expect(page.getByRole("heading", { name: "Reviewed research providers" })).toBeVisible();
  14 |   await expect(page.getByRole("heading", { name: "Healthy connections" })).toBeVisible();
  15 |   await expect(page.locator(".active-market-grid strong", { hasText: "LiteLLM Gateway" })).toBeVisible();
  16 |   for (const provider of ["CME Group", "Cboe FX Spot", "Coinbase Exchange"]) {
  17 |     await expect(page.locator(".active-market-grid strong", { hasText: provider })).toHaveCount(0);
  18 |     await expect(page.getByRole("option", { name: provider })).toHaveCount(1);
  19 |   }
  20 |   await expect(page.getByText(/credentials are write-only/i)).toBeVisible();
  21 |   await expect(page.getByText(/licensing and retention/i)).toBeVisible();
  22 |   await expect(page.getByText(/Research LiteLLM/)).toBeVisible();
  23 |   await expect(page.getByRole("option", { name: "OpenAI Responses" })).toHaveCount(0);
  24 |   await expect(page.getByRole("option", { name: "Anthropic Messages" })).toHaveCount(0);
  25 | 
  26 |   await page.locator("#provider-kind").selectOption("LITELLM_PROXY");
  27 |   await expect(page.getByText(/LiteLLM keeps the underlying provider credentials/i)).toBeVisible();
  28 |   await expect(page.locator('input[name="configuration-base_url"]')).toHaveValue("http://litellm:4000/v1");
  29 |   await expect(page.locator('input[name="credential-virtual_key"]')).toBeVisible();
  30 | 
  31 |   await page.getByRole("button", { name: "Test provider" }).click();
  32 |   await expect(page.getByRole("status")).toContainText("Qualification job qualification-job-1");
  33 | 
  34 |   await page.getByText("Rotate write-only credential").click();
  35 |   await page.getByLabel("New api key").fill("browser-only-secret");
  36 |   await page.getByRole("button", { name: "Rotate credential" }).click();
  37 |   await expect(page.getByRole("status")).toContainText("credential rotated");
  38 |   await expect(page.getByText("browser-only-secret")).toHaveCount(0);
  39 | 
  40 |   await page.getByRole("button", { name: "Disable provider" }).click();
  41 |   await expect(page.getByRole("status")).toContainText("disabled");
  42 | });
  43 | 
```