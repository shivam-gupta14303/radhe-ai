package com.radhe.assistant

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

class SyncWorker(appContext: Context, workerParams: WorkerParameters) :
    CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        return try {
            val retrofit = Retrofit.Builder()
                .baseUrl("http://10.0.2.2:8000/api/v1/")
                .addConverterFactory(GsonConverterFactory.create())
                .build()

            val api = retrofit.create(RadheApiService::class.java)
            val response = api.syncCompanionState(deviceId = "android_default_device")

            if (response.isSuccessful && response.body() != null) {
                val syncData = response.body()!!
                // Check if any high priority WhatsApp approvals or tasks exist
                if (syncData.whatsapp_approvals.isNotEmpty()) {
                    // Trigger notification locally
                }
                Result.success()
            } else {
                Result.retry()
            }
        } catch (e: Exception) {
            e.printStackTrace()
            Result.retry()
        }
    }
}
