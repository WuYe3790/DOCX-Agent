"""agents — 内部 sub-agent 编排层

与 basic_tools/ 平行,但职责不同:
    - basic_tools/  原子工具 (主 agent 可直接调用, 有 schema)
    - agents/       内部编排 worker (主 agent 看不到, 在工具内部被调用)

第一个实现: image_refiner.py (生成图后内部审核-重生循环)
未来可能加: text_polisher.py / style_adjuster.py 等
"""