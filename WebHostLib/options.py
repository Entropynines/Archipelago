import json
import logging
import os
import typing
import collections

import Options
from Utils import local_path
from worlds.AutoWorld import AutoWorldRegister

handled_in_js = {"start_inventory", "local_items", "non_local_items", "start_hints", "start_location_hints",
                 "exclude_locations", "priority_locations"}


def create():
    target_folder = local_path("WebHostLib", "static", "generated")
    yaml_folder = os.path.join(target_folder, "configs")

    Options.generate_yaml_templates(yaml_folder)

    def get_html_doc(option_type: type(Options.Option)) -> str:
        if not option_type.__doc__:
            return "Please document me!"
        return "\n".join(line.strip() for line in option_type.__doc__.split("\n")).strip()

    weighted_options = {
        "baseOptions": {
            "description": "Generated by https://archipelago.gg/",
            "name": "",
            "game": {},
        },
        "games": {},
    }

    for game_name, world in AutoWorldRegister.world_types.items():

        all_options: typing.Dict[str, Options.AssembleOptions] = world.options_dataclass.type_hints
        grouped_options = collections.defaultdict(dict)
        for option_name, option in all_options.items():
            grouped_options[getattr(option, "group_name", "Game Options")][option_name] = option

        # Generate JSON files for player-options pages
        player_options = {
            "baseOptions": {
                "description": f"Generated by https://archipelago.gg/ for {game_name}",
                "game": game_name,
                "name": "",
            },
        }

        game_option_groups = {}

        for group_name, group_options in grouped_options.items():
            if not hasattr(game_option_groups, group_name):
                game_option_groups[group_name] = {}

            for option_name, option in group_options.items():
                if option_name in handled_in_js:
                    pass

                elif issubclass(option, Options.Choice) or issubclass(option, Options.Toggle):
                    game_option_groups[group_name][option_name] = this_option = {
                        "type": "select",
                        "groupName": option.group_name if hasattr(option, "group_name") else None,
                        "displayName": option.display_name if hasattr(option, "display_name") else option_name,
                        "description": get_html_doc(option),
                        "defaultValue": None,
                        "options": []
                    }

                    for sub_option_id, sub_option_name in option.name_lookup.items():
                        if sub_option_name != "random":
                            this_option["options"].append({
                                "name": option.get_option_name(sub_option_id),
                                "value": sub_option_name,
                            })
                        if sub_option_id == option.default:
                            this_option["defaultValue"] = sub_option_name

                    if not this_option["defaultValue"]:
                        this_option["defaultValue"] = "random"

                elif issubclass(option, Options.Range):
                    game_option_groups[group_name][option_name] = {
                        "type": "range",
                        "groupName": option.group_name if hasattr(option, "group_name") else None,
                        "displayName": option.display_name if hasattr(option, "display_name") else option_name,
                        "description": get_html_doc(option),
                        "defaultValue": option.default if hasattr(
                            option, "default") and option.default != "random" else option.range_start,
                        "min": option.range_start,
                        "max": option.range_end,
                    }

                    if issubclass(option, Options.NamedRange):
                        game_option_groups[group_name][option_name]["type"] = 'named_range'
                        game_option_groups[group_name][option_name]["value_names"] = {}
                        for key, val in option.special_range_names.items():
                            game_option_groups[group_name][option_name]["value_names"][key] = val

                elif issubclass(option, Options.ItemSet):
                    game_option_groups[group_name][option_name] = {
                        "type": "items-list",
                        "groupName": option.group_name if hasattr(option, "group_name") else None,
                        "displayName": option.display_name if hasattr(option, "display_name") else option_name,
                        "description": get_html_doc(option),
                        "defaultValue": list(option.default)
                    }

                elif issubclass(option, Options.LocationSet):
                    game_option_groups[group_name][option_name] = {
                        "type": "locations-list",
                        "groupName": option.group_name if hasattr(option, "group_name") else None,
                        "displayName": option.display_name if hasattr(option, "display_name") else option_name,
                        "description": get_html_doc(option),
                        "defaultValue": list(option.default)
                    }

                elif issubclass(option, Options.VerifyKeys) and not issubclass(option, Options.OptionDict):
                    if option.valid_keys:
                        game_option_groups[group_name][option_name] = {
                            "type": "custom-list",
                            "groupName": option.group_name if hasattr(option, "group_name") else None,
                            "displayName": option.display_name if hasattr(option, "display_name") else option_name,
                            "description": get_html_doc(option),
                            "options": list(option.valid_keys),
                            "defaultValue": list(option.default) if hasattr(option, "default") else []
                        }

                else:
                    logging.debug(f"{option} not exported to Web Options.")

        player_options["gameOptionGroups"] = game_option_groups
        print(player_options)

        player_options["presetOptions"] = {}
        for preset_name, preset in world.web.options_presets.items():
            player_options["presetOptions"][preset_name] = {}
            for option_name, option_value in preset.items():
                # Random range type settings are not valid.
                assert (not str(option_value).startswith("random-")), \
                    f"Invalid preset value '{option_value}' for '{option_name}' in '{preset_name}'. Special random " \
                    f"values are not supported for presets."

                # Normal random is supported, but needs to be handled explicitly.
                if option_value == "random":
                    player_options["presetOptions"][preset_name][option_name] = option_value
                    continue

                option = world.options_dataclass.type_hints[option_name].from_any(option_value)
                if isinstance(option, Options.NamedRange) and isinstance(option_value, str):
                    assert option_value in option.special_range_names, \
                        f"Invalid preset value '{option_value}' for '{option_name}' in '{preset_name}'. " \
                        f"Expected {option.special_range_names.keys()} or {option.range_start}-{option.range_end}."

                    # Still use the true value for the option, not the name.
                    player_options["presetOptions"][preset_name][option_name] = option.value
                elif isinstance(option, Options.Range):
                    player_options["presetOptions"][preset_name][option_name] = option.value
                elif isinstance(option_value, str):
                    # For Choice and Toggle options, the value should be the name of the option. This is to prevent
                    # setting a preset for an option with an overridden from_text method that would normally be okay,
                    # but would not be okay for the webhost's current implementation of player options UI.
                    assert option.name_lookup[option.value] == option_value, \
                        f"Invalid option value '{option_value}' for '{option_name}' in preset '{preset_name}'. " \
                        f"Values must not be resolved to a different option via option.from_text (or an alias)."
                    player_options["presetOptions"][preset_name][option_name] = option.current_key
                else:
                    # int and bool values are fine, just resolve them to the current key for webhost.
                    player_options["presetOptions"][preset_name][option_name] = option.current_key

        os.makedirs(os.path.join(target_folder, 'player-options'), exist_ok=True)

        with open(os.path.join(target_folder, 'player-options', game_name + ".json"), "w") as f:
            json.dump(player_options, f, indent=2, separators=(',', ': '))

        if not world.hidden and world.web.options_page is True:
            for group_name, group_options in game_option_groups.items():
                # Add the random option to Choice, TextChoice, and Toggle options
                for option in group_options.values():
                    if option["type"] == "select":
                        option["options"].append({"name": "Random", "value": "random"})

                        if not option["defaultValue"]:
                            option["defaultValue"] = "random"

                weighted_options["baseOptions"]["game"][game_name] = 0
                weighted_options["games"][game_name] = {
                    "gameOptionGroups": game_option_groups,
                    "gameItems": tuple(world.item_names),
                    "gameItemGroups": [
                        group for group in world.item_name_groups.keys() if group != "Everything"
                    ],
                    "gameItemDescriptions": world.item_descriptions,
                    "gameLocations": tuple(world.location_names),
                    "gameLocationGroups": [
                        group for group in world.location_name_groups.keys() if group != "Everywhere"
                    ],
                    "gameLocationDescriptions": world.location_descriptions,
                }

    with open(os.path.join(target_folder, 'weighted-options.json'), "w") as f:
        json.dump(weighted_options, f, indent=2, separators=(',', ': '))

