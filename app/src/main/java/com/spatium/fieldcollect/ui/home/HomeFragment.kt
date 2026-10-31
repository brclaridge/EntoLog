package com.spatium.fieldcollect.ui.home

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.fragment.app.activityViewModels
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import com.spatium.fieldcollect.R
import com.spatium.fieldcollect.databinding.FragmentHomeBinding
import com.spatium.fieldcollect.viewmodel.WifiSyncViewModel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class HomeFragment : Fragment() {

    private var _binding: FragmentHomeBinding? = null
    private val binding get() = _binding!!

    private val wifiSyncViewModel: WifiSyncViewModel by activityViewModels()

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        _binding = FragmentHomeBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        binding.btnNewSpecimen.setOnClickListener {
            findNavController().navigate(R.id.action_home_to_specimen)
        }

        binding.btnNewTrap.setOnClickListener {
            findNavController().navigate(R.id.action_home_to_trap)
        }

        binding.btnViewRecords.setOnClickListener {
            findNavController().navigate(R.id.action_home_to_records)
        }

        binding.btnSync.setOnClickListener {
            val state = wifiSyncViewModel.serverState.value
            if (state is WifiSyncViewModel.ServerState.Running) {
                wifiSyncViewModel.stopServer()
            } else {
                wifiSyncViewModel.startServer()
            }
        }

        viewLifecycleOwner.lifecycleScope.launch {
            wifiSyncViewModel.serverState.collectLatest { state ->
                when (state) {
                    is WifiSyncViewModel.ServerState.Idle -> {
                        binding.btnSync.text = getString(R.string.start_wifi_sync)
                        binding.syncInfo.visibility = View.GONE
                    }
                    is WifiSyncViewModel.ServerState.Running -> {
                        binding.btnSync.text = getString(R.string.stop_wifi_sync)
                        binding.syncInfo.text = getString(
                            R.string.wifi_sync_info,
                            state.ip,
                            state.port,
                            state.token
                        )
                        binding.syncInfo.visibility = View.VISIBLE
                    }
                    is WifiSyncViewModel.ServerState.Error -> {
                        binding.btnSync.text = getString(R.string.start_wifi_sync)
                        binding.syncInfo.visibility = View.GONE
                        Toast.makeText(requireContext(), state.message, Toast.LENGTH_LONG).show()
                    }
                }
            }
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }
}
