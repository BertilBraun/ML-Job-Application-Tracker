Bertil Braun
Applied ML Research Engineer
hi@bertil-braun.de | Karlsruhe, Germany | +49 1525 3810140
linkedin.com/in/bertil-braun

## About

AI engineer with a research background, building end-to-end ML systems across reinforcement learning, computer vision, and LLM pipelines. MSc from KIT with an AI specialization (KI-Profil), completed in half the standard time, and 3+ years of industry experience across startups and large organizations including Mercedes-Benz.

I like hard problems. Whether that means designing a distributed self-play training system for chess, building a multi-object tracking pipeline for video analysis, or developing automated LLM evaluation frameworks — I work across the full stack from research and algorithm design through to production deployment.

Seeking applied ML or research engineering roles with experienced teams and challenging problems.

## Education

**M.Sc. Informatics | AI specialization**
Karlsruhe Institute of Technology (KIT) | 2023 – 2024 | Grade 1.2
- Focus: Machine Learning, AI, Algorithms
- Thesis: Developed multi-phase LLM pipeline for extracting competencies from unstructured documents, including fine-tuning and automated evaluation methods.
- Completed in 1 year, half the standard time for a Master's at KIT.

**B.Sc. Informatics**
Karlsruhe Institute of Technology (KIT) | 2020 – 2023
- Thesis: Investigated bounded software verification for sorting algorithms, focusing on modular techniques to ensure reliability and correctness in implementations.

## Technical Skills

- Programming & Frameworks: Python, C++, PyTorch, NumPy, C#, Java, React
- AI & ML: Reinforcement Learning (AlphaZero), Computer Vision (YOLO, Tracking), LLM pipelines
- Systems & Deployment: Cloud (GCP/Firebase/Modal), Docker, SQL/NoSQL, Full-stack AI systems
- Languages: German (native), English (fluent)

## Experience

**Independent AI Research & Engineering** | Self-directed | 04/2025 – 04/2026 | Tenerife, Spain
Dedicated one year to independent AI research and system development, deliberately stepping back from employment to build at depth across multiple ML domains. Delivered several production-grade and research-grade systems end-to-end.
- Built an AlphaZero-style chess engine from scratch: distributed self-play, custom neural network architecture, ~2100 Elo against Stockfish within a $13 compute budget
- Developed GybeLock, a full windsurfing video intelligence platform: custom YOLO-based detector, multi-object tracking with ILP optimization, RTS smoothing, deployed as a full-stack web application
- Built a fully GPU-resident RL system in JAX (27.6x speedup over CPU baseline, 5,248 updates/sec, zero host-device transfers)
- Additional projects: speech translation pipelines, LLM-based information extraction, automated evaluation frameworks

**Research Assistant - Computer Science** | Karlsruhe Institute of Technology (KIT) | 01/2025 – 04/2025
Conducted research on automated LLM evaluation, resulting in a first-author publication at ACL 2025 Workshop. Designed a multi-LLM pairwise evaluation framework using Elo rating systems to assess output quality at scale without requiring human expert annotation.

**AI Engineer / Master's Thesis** | CAS Software AG | 05/2024 – 12/2024 | Karlsruhe, Germany
Developed a domain-agnostic competency extraction system using LLMs, covering multi-phase pipeline design, fine-tuning, and automated evaluation methods. Work formed the basis of the ACL 2025 publication. Subsequently contributed as AI Engineer to production LLM systems.

**Algorithm Engineer** | 09/2023 – 05/2024 | Karlsruhe, Germany
Worked within a complex in-house constraint satisfaction system (boolean, numerical, and string constraints) for industrial product configurators. Independently researched and prototyped the integration of a Mercedes-specific constraint rule, delivering a viability evaluation and working prototype.

**Working Student – Automation Engineering** | Mercedes-Benz AG | 04/2022 – 04/2023 | Stuttgart, Germany
Built an automation framework used by engineers to set up, run, and evaluate mechanical simulations.

## Publications

**(Towards) Scalable Reliable Automated Evaluation with Large Language Models**
Association for Computational Linguistics 2025 Workshop | 07/2025
Introduced novel evaluation framework for LLM-generated content using pairwise comparisons and Elo rating systems. The method demonstrates significant correlation with expert judgments while reducing human annotation requirements.

## Projects

**GybeLock – Multi-Object Tracking & Video Intelligence System** | 07/2025 – 03/2026
End-to-end system for automatically detecting, tracking, and segmenting individual windsurfers from raw session footage, generating per-athlete highlight videos and motion metadata.
- Trained a custom YOLO-based detector for high-precision athlete recognition
- Designed multi-agent tracking pipeline combining ReID and ILP optimization
- Automated video segmentation, stabilization, and trajectory smoothing
- Full-stack deployment: React frontend, server-side compute backend, DB, authentication

**AlphaZero-Style Chess: General Deep Reinforcement Learning for Board Games** | 01/2023 – 07/2025
Complete deep RL framework implementing AlphaZero methodology for chess and other board games.
- Custom neural network (8×96 layers) trained via self-play
- Distributed self-play on 4 GPUs and 96 CPUs generated ~280k games in 12 hours
- Reached ~2100 Elo against Stockfish within a $13 training budget
- Implemented in Python/C++ with distributed training infrastructure

**Pyro - Collaborative Music Voting App** | 10/2020 – 10/2022
Co-founded and built a mobile app for collaborative music control via Spotify integration. Grew to 80k+ users with clients including bars and clubs. Responsible for backend architecture, real-time voting sync, and Spotify API integration.
