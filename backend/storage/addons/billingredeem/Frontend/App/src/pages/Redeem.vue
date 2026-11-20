<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Gift,
  Loader2,
  CheckCircle2,
  History,
  AlertCircle,
  Sparkles,
  TrendingUp,
} from "@lucide/vue";
import {
  useRedeemAPI,
  type RedeemHistoryItem,
  type RedeemPlanPreview,
} from "@/composables/useRedeemAPI";
import { useToast } from "vue-toastification";

const toast = useToast();
const { loading, error, preview, redeem, getHistory } = useRedeemAPI();

// Redeem form
const codeInput = ref("");
const redeeming = ref(false);
const serverName = ref("");
const chosenLocationId = ref<number | null>(null);
const chosenRealmId = ref<number | null>(null);
const chosenSpellId = ref<number | null>(null);
const trialPlan = ref<RedeemPlanPreview | null>(null);
const freePeriodDays = ref<number | null>(null);
const awaitingSelection = ref(false);

// History
const history = ref<RedeemHistoryItem[]>([]);
const loadingHistory = ref(false);
const historyPage = ref(1);
const historyTotal = ref(0);
const showHistory = ref(false);

const locationOptions = computed(() => {
  const plan = trialPlan.value;
  if (!plan) return [];
  return (plan.location_ids ?? []).map((id) => {
    const raw = plan.location_names?.[String(id)];
    const label = typeof raw === "string" ? raw.trim() : "";
    return { id, label: label || `Location #${id}` };
  });
});

const showLocationSelect = computed(() => locationOptions.value.length > 1);
const showRealmSelect = computed(
  () =>
    !!trialPlan.value?.user_can_choose_realm &&
    (trialPlan.value?.allowed_realms_options?.length ?? 0) > 1
);
const filteredSpells = computed(() => {
  const plan = trialPlan.value;
  if (!plan?.user_can_choose_spell || !plan.allowed_spells_options?.length) {
    return [];
  }
  let realmId: number | null = null;
  if (plan.user_can_choose_realm) {
    if (chosenRealmId.value == null) return [];
    realmId = Number(chosenRealmId.value);
  } else if (plan.realms_id) {
    realmId = Number(plan.realms_id);
  }
  if (realmId == null || Number.isNaN(realmId)) {
    return plan.allowed_spells_options;
  }
  return plan.allowed_spells_options.filter(
    (s) => Number(s.realm_id) === realmId
  );
});
const showSpellSelect = computed(
  () =>
    !!trialPlan.value?.user_can_choose_spell &&
    (trialPlan.value?.allowed_spells_options?.length ?? 0) > 1
);

const canConfirmTrial = computed(() => {
  if (!awaitingSelection.value || !trialPlan.value) return false;
  if (showLocationSelect.value && chosenLocationId.value == null) return false;
  if (showRealmSelect.value && chosenRealmId.value == null) return false;
  if (showSpellSelect.value) {
    if (filteredSpells.value.length === 0) return false;
    if (chosenSpellId.value == null) return false;
  }
  return true;
});

const resetTrialSelection = () => {
  trialPlan.value = null;
  freePeriodDays.value = null;
  awaitingSelection.value = false;
  serverName.value = "";
  chosenLocationId.value = null;
  chosenRealmId.value = null;
  chosenSpellId.value = null;
};

const seedDefaultsFromPlan = (plan: RedeemPlanPreview) => {
  const locations = plan.location_ids ?? [];
  if (locations.length === 1) {
    chosenLocationId.value = locations[0];
  }
  if (
    plan.user_can_choose_realm &&
    plan.allowed_realms_options?.length === 1
  ) {
    chosenRealmId.value = plan.allowed_realms_options[0].id;
  }
  if (
    plan.user_can_choose_spell &&
    plan.allowed_spells_options?.length === 1
  ) {
    chosenSpellId.value = plan.allowed_spells_options[0].id;
  }
  serverName.value = plan.name || "";
};

const executeRedeem = async () => {
  const code = codeInput.value.trim();
  if (!code) {
    toast.error("Please enter a code");
    return;
  }

  redeeming.value = true;
  try {
    const result = await redeem({
      code,
      server_name: serverName.value.trim() || undefined,
      chosen_location_id:
        chosenLocationId.value != null
          ? Number(chosenLocationId.value)
          : undefined,
      chosen_realm_id:
        chosenRealmId.value != null ? Number(chosenRealmId.value) : undefined,
      chosen_spell_id:
        chosenSpellId.value != null ? Number(chosenSpellId.value) : undefined,
    });
    if (result.reward_type === "billing_plan_trial") {
      toast.success(
        `Trial activated for ${result.free_period_days || 0} day(s). Billing will start after the trial period.`
      );
    } else {
      toast.success(
        `Successfully redeemed ${result.amount_formatted}! Your new balance is ${result.new_credits_formatted}`
      );
    }
    codeInput.value = "";
    resetTrialSelection();
    if (showHistory.value) {
      await loadHistory();
    }
  } catch (err) {
    const errorMsg =
      err instanceof Error ? err.message : "Failed to redeem code";
    toast.error(errorMsg);
  } finally {
    redeeming.value = false;
  }
};

// Handle redeem / preview
const handleRedeem = async () => {
  const code = codeInput.value.trim();
  if (!code) {
    toast.error("Please enter a code");
    return;
  }

  if (awaitingSelection.value) {
    if (!canConfirmTrial.value) {
      toast.error("Please complete the server configuration");
      return;
    }
    await executeRedeem();
    return;
  }

  redeeming.value = true;
  let shouldRedeemNow = false;
  try {
    const previewResult = await preview(code);
    if (previewResult.reward_type === "billing_plan_trial") {
      freePeriodDays.value = previewResult.free_period_days ?? null;
      if (previewResult.plan) {
        trialPlan.value = previewResult.plan;
        seedDefaultsFromPlan(previewResult.plan);
      }
      if (previewResult.requires_selection) {
        awaitingSelection.value = true;
        toast.info(
          "Select your server configuration to activate this trial code."
        );
        return;
      }
    }
    shouldRedeemNow = true;
  } catch (err) {
    const errorMsg =
      err instanceof Error ? err.message : "Failed to redeem code";
    toast.error(errorMsg);
  } finally {
    redeeming.value = false;
  }

  if (shouldRedeemNow) {
    await executeRedeem();
  }
};

const cancelSelection = () => {
  resetTrialSelection();
};

// Load history
const loadHistory = async () => {
  loadingHistory.value = true;
  try {
    const result = await getHistory(20, (historyPage.value - 1) * 20);
    history.value = result.history;
    historyTotal.value = result.total;
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "Failed to load history");
  } finally {
    loadingHistory.value = false;
  }
};

// Toggle history
const toggleHistory = async () => {
  showHistory.value = !showHistory.value;
  if (showHistory.value && history.value.length === 0) {
    await loadHistory();
  }
};

// Format date
const formatDate = (dateString: string): string => {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

onMounted(() => {
  // Focus input on mount
  setTimeout(() => {
    const input = document.querySelector(
      'input[type="text"]'
    ) as HTMLInputElement;
    if (input) {
      input.focus();
    }
  }, 100);
});
</script>

<template>
  <div class="min-h-screen p-4 md:p-8">
    <div class="max-w-5xl mx-auto space-y-8">
      <!-- Header Section -->
      <div class="text-center space-y-4">
        <div class="flex items-center justify-center gap-3">
          <div class="relative">
            <div
              class="absolute inset-0 bg-primary/20 blur-2xl rounded-full"
            ></div>
            <Gift class="relative h-12 w-12 text-primary" />
          </div>
        </div>
        <div>
          <h1
            class="text-5xl font-bold bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent"
          >
            Redeem Codes
          </h1>
          <p class="text-lg text-muted-foreground mt-2">
            Enter your redemption code to instantly receive credits or activate a trial
          </p>
        </div>
      </div>

      <!-- Main Redeem Card -->
      <Card class="p-8 md:p-10 border-2 shadow-xl bg-card/50 backdrop-blur-sm">
        <div class="space-y-6">
          <div class="flex items-center gap-3 mb-6">
            <div class="p-2 rounded-lg bg-primary/10">
              <Sparkles class="h-6 w-6 text-primary" />
            </div>
            <div>
              <h2 class="text-2xl font-bold">Enter Your Code</h2>
              <p class="text-sm text-muted-foreground">
                Paste or type your redemption code below
              </p>
            </div>
          </div>

          <div class="space-y-4">
            <div class="relative">
              <Input
                id="code"
                v-model="codeInput"
                type="text"
                placeholder="REDEEM-CODE-123"
                class="h-14 text-lg font-mono uppercase tracking-wider text-center border-2 focus:border-primary transition-colors"
                :disabled="redeeming || loading || awaitingSelection"
                @keyup.enter="handleRedeem"
              />
              <div class="absolute right-3 top-1/2 -translate-y-1/2">
                <Gift class="h-5 w-5 text-muted-foreground" />
              </div>
            </div>

            <div
              v-if="awaitingSelection && trialPlan"
              class="space-y-4 rounded-xl border border-border bg-muted/30 p-4"
            >
              <div>
                <p class="text-sm font-medium text-foreground">
                  Activate trial: {{ trialPlan.name }}
                </p>
                <p class="text-xs text-muted-foreground mt-1">
                  {{ freePeriodDays || 0 }} free day(s). Choose where your server will be created.
                </p>
              </div>

              <div>
                <label class="block text-xs font-medium text-muted-foreground mb-1.5">
                  Server name
                </label>
                <Input
                  v-model="serverName"
                  type="text"
                  placeholder="My server"
                  class="h-10"
                  :disabled="redeeming || loading"
                />
              </div>

              <div v-if="showLocationSelect">
                <label class="block text-xs font-medium text-muted-foreground mb-1.5">
                  Location <span class="text-red-400">*</span>
                </label>
                <select
                  v-model="chosenLocationId"
                  class="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  :disabled="redeeming || loading"
                >
                  <option :value="null" disabled>Select a location…</option>
                  <option
                    v-for="loc in locationOptions"
                    :key="loc.id"
                    :value="loc.id"
                  >
                    {{ loc.label }}
                  </option>
                </select>
              </div>

              <div v-if="showRealmSelect">
                <label class="block text-xs font-medium text-muted-foreground mb-1.5">
                  Nest <span class="text-red-400">*</span>
                </label>
                <select
                  v-model="chosenRealmId"
                  class="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  :disabled="redeeming || loading"
                  @change="chosenSpellId = null"
                >
                  <option :value="null" disabled>Select a nest…</option>
                  <option
                    v-for="realm in trialPlan.allowed_realms_options"
                    :key="realm.id"
                    :value="realm.id"
                  >
                    {{ realm.name }}
                  </option>
                </select>
              </div>

              <div v-if="showSpellSelect">
                <label class="block text-xs font-medium text-muted-foreground mb-1.5">
                  Egg (server type) <span class="text-red-400">*</span>
                </label>
                <p
                  v-if="showRealmSelect && chosenRealmId == null"
                  class="text-xs text-muted-foreground mb-1.5"
                >
                  Select a nest first.
                </p>
                <select
                  v-model="chosenSpellId"
                  class="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  :disabled="
                    redeeming ||
                    loading ||
                    (showRealmSelect && chosenRealmId == null) ||
                    filteredSpells.length === 0
                  "
                >
                  <option :value="null" disabled>Select a server type…</option>
                  <option
                    v-for="spell in filteredSpells"
                    :key="spell.id"
                    :value="spell.id"
                  >
                    {{ spell.name }}
                  </option>
                </select>
              </div>

              <div class="flex gap-2">
                <Button
                  variant="outline"
                  class="flex-1"
                  :disabled="redeeming || loading"
                  @click="cancelSelection"
                >
                  Cancel
                </Button>
                <Button
                  class="flex-1"
                  :disabled="redeeming || loading || !canConfirmTrial"
                  @click="handleRedeem"
                >
                  <Loader2 v-if="redeeming" class="mr-2 h-4 w-4 animate-spin" />
                  Activate Trial
                </Button>
              </div>
            </div>

            <Button
              v-else
              @click="handleRedeem"
              :disabled="redeeming || loading || !codeInput.trim()"
              class="w-full h-12 text-lg font-semibold shadow-lg hover:shadow-xl transition-all"
              size="lg"
            >
              <Loader2 v-if="redeeming" class="mr-2 h-5 w-5 animate-spin" />
              <Gift v-else class="mr-2 h-5 w-5" />
              {{ redeeming ? "Redeeming..." : "Redeem Code" }}
            </Button>
          </div>

          <Alert v-if="error" variant="destructive" class="border-2">
            <AlertCircle class="h-4 w-4" />
            <AlertDescription class="font-medium">{{ error }}</AlertDescription>
          </Alert>

          <!-- Info Box -->
          <div class="mt-6 p-4 rounded-lg bg-muted/50 border border-border/50">
            <div class="flex items-start gap-3">
              <TrendingUp class="h-5 w-5 text-primary mt-0.5 shrink-0" />
              <div class="text-sm text-muted-foreground">
                <p class="font-medium text-foreground mb-1">How it works</p>
                <p>
                  Enter your redemption code above and click "Redeem Code". Credit
                  codes are applied instantly. Trial codes may ask you to choose
                  location, nest, or server type before activation.
                </p>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <!-- History Section -->
      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <History class="h-5 w-5 text-primary" />
            <h2 class="text-2xl font-bold">Redemption History</h2>
          </div>
          <Button
            variant="outline"
            @click="toggleHistory"
            :disabled="loadingHistory"
            class="gap-2"
          >
            <History class="h-4 w-4" />
            {{ showHistory ? "Hide" : "Show" }} History
            <Badge v-if="historyTotal > 0" variant="secondary" class="ml-2">
              {{ historyTotal }}
            </Badge>
          </Button>
        </div>

        <Card
          v-if="showHistory"
          class="p-6 border-2 shadow-lg bg-card/50 backdrop-blur-sm"
        >
          <div class="space-y-4">
            <div v-if="loadingHistory" class="flex justify-center py-12">
              <Loader2 class="h-8 w-8 animate-spin text-primary" />
            </div>

            <div
              v-else-if="history.length === 0"
              class="text-center py-12 space-y-3"
            >
              <div class="flex justify-center">
                <div class="p-4 rounded-full bg-muted">
                  <Gift class="h-8 w-8 text-muted-foreground" />
                </div>
              </div>
              <p class="text-muted-foreground font-medium">
                No redemption history yet
              </p>
              <p class="text-sm text-muted-foreground">
                Your redeemed codes will appear here
              </p>
            </div>

            <div v-else class="space-y-3">
              <div
                v-for="item in history"
                :key="item.id"
                class="group flex items-center justify-between p-5 border-2 rounded-xl hover:border-primary/50 hover:bg-primary/5 transition-all duration-200 cursor-pointer"
              >
                <div class="flex items-center gap-4 flex-1">
                  <div
                    class="p-3 rounded-lg bg-green-500/10 group-hover:bg-green-500/20 transition-colors"
                  >
                    <CheckCircle2
                      class="h-6 w-6 text-green-600 dark:text-green-400"
                    />
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-3 mb-1.5">
                      <Badge
                        variant="outline"
                        class="font-mono text-sm font-semibold px-3 py-1"
                      >
                        {{ item.code }}
                      </Badge>
                      <span
                        v-if="item.amount"
                        class="text-lg font-bold text-green-600 dark:text-green-400"
                      >
                        +{{ item.amount }} credits
                      </span>
                    </div>
                    <p class="text-sm text-muted-foreground">
                      {{ formatDate(item.used_at) }}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <!-- Pagination -->
            <div
              v-if="historyTotal > 20"
              class="flex items-center justify-between pt-6 border-t"
            >
              <Button
                variant="outline"
                :disabled="historyPage === 1 || loadingHistory"
                @click="
                  historyPage--;
                  loadHistory();
                "
                class="gap-2"
              >
                <span>Previous</span>
              </Button>
              <span class="text-sm text-muted-foreground font-medium">
                Page {{ historyPage }} of {{ Math.ceil(historyTotal / 20) }}
              </span>
              <Button
                variant="outline"
                :disabled="
                  historyPage >= Math.ceil(historyTotal / 20) || loadingHistory
                "
                @click="
                  historyPage++;
                  loadHistory();
                "
                class="gap-2"
              >
                <span>Next</span>
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  </div>
</template>
