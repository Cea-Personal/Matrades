# LiteLLM gateway

TraderX can use LiteLLM as one advisory-model gateway instead of creating a separate
TraderX integration for every model vendor. LiteLLM holds the upstream provider
credentials and exposes only configured model aliases to TraderX.

1. Set a long random `LITELLM_MASTER_KEY` in `deploy/.env`. TraderX prefixes it
   internally for LiteLLM's required `sk-` key format; do not add that prefix yourself.
2. Start the optional service:

   ```sh
   docker compose -f deploy/compose.yaml --profile llm-gateway up -d litellm
   ```

3. In TraderX, go to **Integrations → Configure LiteLLM models** and add an alias,
   provider model ID, and provider key. The key is write-only and saved through the
   private LiteLLM administration API—do not edit `config.yaml`.
4. In **Reviewed research providers**, select **LiteLLM
   Gateway**, use `http://litellm:4000/v1` as the base URL, and enter a LiteLLM virtual
   key. Then test and enable the integration.
5. In **Markets**, select LiteLLM Gateway and enter an alias shown in **Configured aliases**.

The LiteLLM container is private to the Compose network. Its `provider-egress` attachment
is for configured upstream model providers; TraderX still sends advisory-only requests with
no tools and a strict JSON response schema.
