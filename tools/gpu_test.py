"""GPU Test Skript."""

import time
import torch

print("CUDA verfügbar:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
    print("CUDA Version:", torch.version.cuda)

    device = torch.device("cuda")

    # Großer Tensor (ca. 1 GB)
    SIZE = 16000

    print("Erzeuge Tensor...")
    a = torch.randn(SIZE, SIZE, device=device)
    b = torch.randn(SIZE, SIZE, device=device)

    print("Starte Matrixmultiplikation...")
    torch.cuda.synchronize()
    start = time.time()

    c = torch.matmul(a, b)

    torch.cuda.synchronize()
    end = time.time()

    print("Fertig.")
    print("Zeit:", round(end - start, 2), "Sekunden")

    print("GPU Speicherverbrauch:")
    print(torch.cuda.memory_allocated() / 1024**3, "GB")

else:
    print("Keine CUDA GPU erkannt.")
