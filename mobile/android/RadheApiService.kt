package com.radhe.assistant

import retrofit2.Response
import retrofit2.http.*

data class ChatMessageRequest(val message: String, val user_id: String = "mobile_user")
data class ChatResponse(val response: String, val intent: String, val latency_ms: Double)
data class DailyBriefingResponse(val language: String, val briefing: Map<String, Any>)
data class ApprovalCard(val contact: String, val incoming: String, val draft: String)
data class WaterLogPayload(val amount_ml: Double)
data class MobileSyncResponse(
    val timestamp: String,
    val tasks: List<Map<String, Any>>,
    val whatsapp_approvals: List<ApprovalCard>,
    val health: Map<String, Any>
)

interface RadheApiService {

    @GET("status")
    suspend fun getStatus(): Response<Map<String, Any>>

    @POST("chat")
    suspend fun sendMessage(@Body req: ChatMessageRequest): Response<ChatResponse>

    @GET("briefing")
    suspend fun getDailyBriefing(@Query("language") language: String = "hinglish"): Response<DailyBriefingResponse>

    @GET("whatsapp/approvals")
    suspend fun getPendingApprovals(): Response<List<ApprovalCard>>

    @POST("whatsapp/approve")
    suspend fun approveReply(): Response<Map<String, Any>>

    @POST("whatsapp/reject")
    suspend fun rejectReply(): Response<Map<String, Any>>

    @POST("health/water")
    suspend fun logWater(@Body req: WaterLogPayload): Response<Map<String, Any>>

    @GET("mobile/sync")
    suspend fun syncCompanionState(@Query("device_id") deviceId: String): Response<MobileSyncResponse>
}
