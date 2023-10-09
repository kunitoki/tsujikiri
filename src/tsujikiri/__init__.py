__version__ = "0.0.1"

if __name__ == "__main__":
    import argparse
    from .inspect import run_main

    parser = argparse.ArgumentParser(description="Generic C++ Binding Generator")
    parser.add_argument("--inspector", default="juce_core", help="Name of the inspector to use")
    parser.add_argument("--generator", default="juce_generator", help="Name of the generator to use")
    parser.add_argument("--classname", help="Name of the single class, or None for all classes")
    args = parser.parse_args()

    run_main(args.inspector, args.generator, args.classname)
