import { ref } from "vue";
import axios from "axios";
import type { AxiosError } from "axios";

export interface RedeemPlanOption {
  id: number;
  name: string;
  realm_id?: number;
}

export interface RedeemPlanPreview {
  id: number;
  name: string;
  location_ids: number[];
  location_names: Record<string, string>;
  user_can_choose_realm: boolean;
  user_can_choose_spell: boolean;
  allowed_realms_options: RedeemPlanOption[];
  allowed_spells_options: RedeemPlanOption[];
  realms_id: number | null;
}

export interface RedeemPreviewResponse {
  code: string;
  reward_type: "credits" | "billing_plan_trial";
  amount: number;
  amount_formatted: string;
  plan_id?: number | null;
  free_period_days?: number | null;
  plan?: RedeemPlanPreview | null;
  requires_selection?: boolean;
}

export interface RedeemPayload {
  code: string;
  server_name?: string;
  chosen_location_id?: number;
  chosen_realm_id?: number;
  chosen_spell_id?: number;
}

export interface RedeemResponse {
  code: string;
  amount: number;
  reward_type?: "credits" | "billing_plan_trial";
  plan_id?: number | null;
  free_period_days?: number | null;
  subscription?: Record<string, unknown> | null;
  amount_formatted: string;
  new_credits: number;
  new_credits_formatted: string;
}

export interface RedeemHistoryItem {
  id: number;
  code_id: number;
  user_id: number;
  used_at: string;
  created_at: string;
  updated_at: string;
  code?: string;
  amount?: number;
}

export interface RedeemHistory {
  history: RedeemHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export function useRedeemAPI() {
  const loading = ref(false);
  const error = ref<string | null>(null);

  const handleError = (err: unknown): string => {
    if (axios.isAxiosError(err)) {
      const axiosError = err as AxiosError<{
        message?: string;
        error_message?: string;
        error?: string;
      }>;
      return (
        axiosError.response?.data?.message ||
        axiosError.response?.data?.error_message ||
        axiosError.response?.data?.error ||
        axiosError.message ||
        "An error occurred"
      );
    }
    if (err instanceof Error) {
      return err.message;
    }
    return "An unknown error occurred";
  };

  const preview = async (code: string): Promise<RedeemPreviewResponse> => {
    loading.value = true;
    error.value = null;

    try {
      const response = await axios.post("/api/user/billingredeem/preview", {
        code: code.trim(),
      });
      if (response.data && response.data.success) {
        return response.data.data;
      }
      throw new Error(response.data?.message || "Failed to preview code");
    } catch (err) {
      const errorMsg = handleError(err);
      error.value = errorMsg;
      throw new Error(errorMsg);
    } finally {
      loading.value = false;
    }
  };

  // Redeem a code
  const redeem = async (payload: RedeemPayload): Promise<RedeemResponse> => {
    loading.value = true;
    error.value = null;

    try {
      const response = await axios.post("/api/user/billingredeem/redeem", {
        code: payload.code.trim(),
        server_name: payload.server_name,
        chosen_location_id: payload.chosen_location_id,
        chosen_realm_id: payload.chosen_realm_id,
        chosen_spell_id: payload.chosen_spell_id,
      });
      if (response.data && response.data.success) {
        return response.data.data;
      }
      throw new Error(response.data?.message || "Failed to redeem code");
    } catch (err) {
      const errorMsg = handleError(err);
      error.value = errorMsg;
      throw new Error(errorMsg);
    } finally {
      loading.value = false;
    }
  };

  // Get redemption history
  const getHistory = async (
    limit: number = 50,
    offset: number = 0
  ): Promise<RedeemHistory> => {
    loading.value = true;
    error.value = null;

    try {
      const response = await axios.get("/api/user/billingredeem/history", {
        params: { limit, offset },
      });
      if (response.data && response.data.success) {
        return response.data.data;
      }
      throw new Error("Failed to fetch redemption history");
    } catch (err) {
      const errorMsg = handleError(err);
      error.value = errorMsg;
      throw new Error(errorMsg);
    } finally {
      loading.value = false;
    }
  };

  return {
    loading,
    error,
    preview,
    redeem,
    getHistory,
  };
}
