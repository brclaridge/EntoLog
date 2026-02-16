package com.spatium.fieldcollect.ui.adapter

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.spatium.fieldcollect.camera.CameraHelper
import com.spatium.fieldcollect.databinding.ItemPhotoBinding

class PhotoAdapter(
    private val photoPaths: List<String>
) : RecyclerView.Adapter<PhotoAdapter.ViewHolder>() {

    inner class ViewHolder(private val binding: ItemPhotoBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(path: String) {
            val bitmap = CameraHelper.loadBitmap(path, sampleSize = 2)
            binding.ivPhoto.setImageBitmap(bitmap)
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemPhotoBinding.inflate(
            LayoutInflater.from(parent.context), parent, false
        )
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(photoPaths[position])
    }

    override fun getItemCount() = photoPaths.size
}
